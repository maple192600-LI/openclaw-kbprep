import { readFile } from "node:fs/promises";
import { callWorker, type WorkerResult } from "./worker.js";

type PluginConfig = {
  ai_review_provider?: string;
  ai_review_model?: string;
  device_override?: "auto" | "cuda" | "cpu";
  max_cpu_threads?: number;
  min_free_memory_gb?: number;
};

type AiReviewParams = {
  mode?: "rules_only" | "rules_plus_review_pack" | "ai_review";
  ai_review_provider?: string;
  ai_review_model?: string;
};

type AiReviewContext = {
  api: {
    runtime?: {
      subagent?: {
        run: (params: {
          sessionKey: string;
          message: string;
          provider?: string;
          model?: string;
          extraSystemPrompt?: string;
          lane?: string;
          lightContext?: boolean;
          deliver?: boolean;
          idempotencyKey?: string;
        }) => Promise<{ runId: string }>;
        waitForRun: (params: { runId: string; timeoutMs?: number }) => Promise<{ status: string; error?: string }>;
        getSessionMessages: (params: { sessionKey: string; limit?: number }) => Promise<{ messages: unknown[] }>;
      };
    };
  };
  toolCallId: string;
  signal?: AbortSignal;
};

const REVIEW_PACK_MAX_CHARS = 80_000;
const REVIEW_PACK_BATCH_TARGET_CHARS = 60_000;
const AI_REVIEW_MAX_ATTEMPTS = 2;
const AI_REVIEW_ALLOWED_FIELDS = new Set(["status", "risk_tags", "reason", "confidence"]);
const AI_REVIEW_ALLOWED_STATUSES = new Set(["keep", "discard", "evidence", "review"]);

export async function maybeRunAiReview<T extends Record<string, unknown>>(
  result: WorkerResult<T>,
  params: AiReviewParams,
  config: PluginConfig,
  context: AiReviewContext,
  opts: {
    pythonPath: string;
    timeoutMs: number;
    workerConfig: Record<string, unknown>;
  },
): Promise<WorkerResult<T>> {
  if (params.mode !== "ai_review" || !result.ok) {
    return result;
  }

  const subagent = context.api.runtime?.subagent;
  const runDir = String(result.data?.run_dir ?? "");
  const reviewPackPath = String((result.data?.outputs as Record<string, unknown> | undefined)?.review_pack ?? "");

  if (!subagent || !runDir || !reviewPackPath) {
    return withAiWarning(result, "W_LLM_REVIEW_SKIPPED: AI review unavailable or review_pack missing.");
  }

  let reviewPack = "";
  try {
    reviewPack = await readFile(reviewPackPath, "utf-8");
  } catch (err) {
    return withAiWarning(result, `W_LLM_REVIEW_SKIPPED: could not read review_pack.json (${String(err)}).`);
  }

  const batches = buildReviewBatches(reviewPack);
  if (!batches.length) {
    return withAiWarning(result, "W_LLM_REVIEW_SKIPPED: review_pack.json could not be split into review batches.");
  }

  const combinedPatch: unknown[] = [];
  const aiWarnings: string[] = [];
  let failedBatches = 0;
  for (const [index, batch] of batches.entries()) {
    let accepted = false;
    for (let attempt = 1; attempt <= AI_REVIEW_MAX_ATTEMPTS; attempt += 1) {
      const sessionKey = `kbprep-review:${context.toolCallId}:${Date.now()}:${index + 1}:${attempt}`;
      const message = buildReviewPrompt(batch, index + 1, batches.length, attempt);

      const run = await subagent.run({
        sessionKey,
        message,
        provider: params.ai_review_provider ?? config.ai_review_provider,
        model: params.ai_review_model ?? config.ai_review_model,
        extraSystemPrompt: AI_REVIEW_SYSTEM_PROMPT,
        lane: "kbprep-review",
        lightContext: true,
        deliver: false,
        idempotencyKey: `${context.toolCallId}:${index + 1}:${attempt}`,
      });

      const waited = await subagent.waitForRun({ runId: run.runId, timeoutMs: opts.timeoutMs });
      if (waited.status !== "ok") {
        aiWarnings.push(`W_LLM_REVIEW_BATCH_ATTEMPT_FAILED: batch ${index + 1}/${batches.length} attempt ${attempt}/${AI_REVIEW_MAX_ATTEMPTS} ${waited.status}${waited.error ? ` (${waited.error})` : ""}.`);
        continue;
      }

      const messages = await subagent.getSessionMessages({ sessionKey, limit: 20 });
      const patch = extractJsonPatch(messages.messages);
      if (!patch) {
        aiWarnings.push(`W_LLM_REVIEW_BATCH_ATTEMPT_FAILED: batch ${index + 1}/${batches.length} attempt ${attempt}/${AI_REVIEW_MAX_ATTEMPTS} did not return a JSON Patch array.`);
        continue;
      }

      const validation = validateAiReviewPatch(patch);
      if (validation.rejected.length) {
        aiWarnings.push(formatRejectedPatchWarning(index + 1, batches.length, attempt, validation.rejected));
      }
      if (validation.valid.length) {
        combinedPatch.push(...validation.valid);
        accepted = true;
        break;
      }
      if (patch.length === 0) {
        accepted = true;
        break;
      }
    }
    if (!accepted) {
      failedBatches += 1;
      aiWarnings.push(`W_LLM_REVIEW_BATCH_SKIPPED: batch ${index + 1}/${batches.length} did not produce any safe patch operations.`);
    }
  }

  if (combinedPatch.length === 0 && failedBatches === batches.length) {
    return {
      ...result,
      warnings: [...(result.warnings ?? []), ...aiWarnings, "W_LLM_REVIEW_SKIPPED: all AI review batches failed."],
    };
  }

  const applied = await callWorker<T>("apply_review", {
    run_dir: runDir,
    patch_json: combinedPatch,
  }, {
    pythonPath: opts.pythonPath,
    timeoutMs: 120_000,
    signal: context.signal,
    config: opts.workerConfig,
  });

  if (!applied.ok) {
    return withAiWarning(result, `W_LLM_REVIEW_SKIPPED: AI patch was rejected (${applied.error?.message ?? "unknown error"}).`);
  }

  const originalData = (result.data ?? {}) as Record<string, unknown>;
  const appliedData = (applied.data ?? {}) as Record<string, unknown>;
  const originalOutputs = (originalData.outputs ?? {}) as Record<string, unknown>;
  const updatedOutputs = (appliedData.updated_outputs ?? {}) as Record<string, unknown>;

  return {
    ...applied,
    data: ({
      ...originalData,
      ...appliedData,
      run_id: originalData.run_id,
      run_dir: originalData.run_dir,
      outputs: {
        ...originalOutputs,
        ...updatedOutputs,
      },
      latest_outputs: appliedData.latest_outputs ?? originalData.latest_outputs,
      ai_review: {
        applied: appliedData.applied ?? 0,
        rejected: appliedData.rejected ?? 0,
        rejected_details: appliedData.rejected_details ?? [],
        published: appliedData.published ?? false,
        batches: batches.length,
        patch_ops: combinedPatch.length,
      },
    } as unknown) as T,
    warnings: [...(result.warnings ?? []), ...aiWarnings, ...(applied.warnings ?? [])],
  };
}

function buildReviewPrompt(reviewPack: string, batchNumber = 1, batchCount = 1, attempt = 1): string {
  return [
    `Review this kbprep review_pack.json batch ${batchNumber}/${batchCount}.`,
    "Return ONLY an RFC 6902 JSON Patch array.",
    "Allowed patch paths must be exactly /blocks/{block_id}/status, /blocks/{block_id}/risk_tags, /blocks/{block_id}/reason, or /blocks/{block_id}/confidence.",
    "Allowed ops: replace status/reason/confidence/risk_tags, or add a single risk_tags string.",
    "Allowed statuses are keep, discard, evidence, review.",
    "Never rewrite text. Never summarize. Never discard steps, prompts, code, tables, tool names, numbers, parameters, links, or concrete examples.",
    "If context is insufficient, set status to review.",
    attempt > 1 ? "Previous response was invalid or unsafe. Return a valid patch array only, or [] if no safe change is needed." : "",
    "",
    reviewPack,
  ].filter(Boolean).join("\n");
}

function buildReviewBatches(reviewPack: string): string[] {
  if (reviewPack.length <= REVIEW_PACK_MAX_CHARS) return [reviewPack];

  let parsed: unknown;
  try {
    parsed = JSON.parse(reviewPack);
  } catch {
    return [];
  }
  if (!parsed || typeof parsed !== "object") return [];

  const pack = parsed as Record<string, unknown>;
  const blocks = Array.isArray(pack.blocks) ? pack.blocks : [];
  if (!blocks.length) return [JSON.stringify({ ...pack, blocks: [] }, null, 2)];

  const batches: string[] = [];
  let current: unknown[] = [];
  for (const block of blocks) {
    const candidate = serializeReviewBatch(pack, [...current, block]);
    if (candidate.length > REVIEW_PACK_BATCH_TARGET_CHARS && current.length > 0) {
      batches.push(serializeReviewBatch(pack, current));
      current = [block];
    } else {
      current.push(block);
    }
  }
  if (current.length) batches.push(serializeReviewBatch(pack, current));

  return batches;
}

function serializeReviewBatch(pack: Record<string, unknown>, blocks: unknown[]): string {
  const batched = {
    ...pack,
    batching: {
      original_block_count: Array.isArray(pack.blocks) ? pack.blocks.length : blocks.length,
      batch_block_count: blocks.length,
    },
    blocks,
  };
  return JSON.stringify(batched, null, 2);
}

const AI_REVIEW_SYSTEM_PROMPT = [
  "You are a conservative knowledge-base cleaning reviewer.",
  "Your job is only to classify existing blocks as keep, discard, evidence, or review.",
  "You must not rewrite, compress, paraphrase, or summarize source text.",
  "Prefer keep or review when a block might contain usable knowledge.",
].join(" ");

function extractJsonPatch(messages: unknown[]): unknown[] | null {
  for (const message of [...messages].reverse()) {
    const text = stringifyMessage(message);
    const parsed = parseFirstJsonArray(text);
    if (parsed && parsed.every((item) => typeof item === "object" && item !== null && "op" in item && "path" in item)) {
      return parsed;
    }
  }
  return null;
}

function validateAiReviewPatch(patch: unknown[]): { valid: unknown[]; rejected: string[] } {
  const valid: unknown[] = [];
  const rejected: string[] = [];

  for (const item of patch) {
    if (!item || typeof item !== "object" || Array.isArray(item)) {
      rejected.push("operation is not an object");
      continue;
    }
    const op = item as Record<string, unknown>;
    const opType = op.op;
    const path = op.path;
    const value = op.value;
    if (opType !== "replace" && opType !== "add") {
      rejected.push(`unsupported op ${String(opType)}`);
      continue;
    }
    if (typeof path !== "string") {
      rejected.push("path must be a string");
      continue;
    }
    const parts = path.split("/").filter(Boolean);
    if (parts.length !== 3 || parts[0] !== "blocks") {
      rejected.push(`invalid path ${path}`);
      continue;
    }
    const field = parts[2];
    if (!AI_REVIEW_ALLOWED_FIELDS.has(field)) {
      rejected.push(`field ${field} is not allowed`);
      continue;
    }

    const valueError = validateAiReviewPatchValue(opType, field, value);
    if (valueError) {
      rejected.push(valueError);
      continue;
    }

    valid.push(item);
  }

  return { valid, rejected };
}

function validateAiReviewPatchValue(opType: "replace" | "add", field: string, value: unknown): string | null {
  if (field === "risk_tags" && opType === "add") {
    return typeof value === "string" ? null : "risk_tags add value must be a string";
  }
  if (opType !== "replace") {
    return `add is not supported for field ${field}`;
  }
  if (field === "status") {
    return typeof value === "string" && AI_REVIEW_ALLOWED_STATUSES.has(value) ? null : `invalid status ${String(value)}`;
  }
  if (field === "risk_tags") {
    return Array.isArray(value) && value.every((item) => typeof item === "string") ? null : "risk_tags replace value must be a string array";
  }
  if (field === "reason") {
    return typeof value === "string" ? null : "reason must be a string";
  }
  if (field === "confidence") {
    return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1 ? null : "confidence must be a number between 0 and 1";
  }
  return `field ${field} is not allowed`;
}

function formatRejectedPatchWarning(batchNumber: number, batchCount: number, attempt: number, rejected: string[]): string {
  const shown = rejected.slice(0, 3).join("; ");
  const suffix = rejected.length > 3 ? `; ${rejected.length - 3} more` : "";
  return `W_LLM_REVIEW_PATCH_OP_REJECTED: batch ${batchNumber}/${batchCount} attempt ${attempt}/${AI_REVIEW_MAX_ATTEMPTS} rejected ${rejected.length} unsafe op(s): ${shown}${suffix}.`;
}

function stringifyMessage(message: unknown): string {
  if (typeof message === "string") return message;
  if (message && typeof message === "object") {
    const record = message as Record<string, unknown>;
    for (const key of ["content", "text", "message", "body"]) {
      const value = record[key];
      if (typeof value === "string") return value;
    }
  }
  return JSON.stringify(message);
}

function parseFirstJsonArray(text: string): unknown[] | null {
  const fenced = text.match(/```(?:json)?\s*([\s\S]*?)```/i);
  const candidates = fenced ? [fenced[1], text] : [text];
  for (const candidate of candidates) {
    const start = candidate.indexOf("[");
    const end = candidate.lastIndexOf("]");
    if (start < 0 || end <= start) continue;
    try {
      const parsed = JSON.parse(candidate.slice(start, end + 1));
      if (Array.isArray(parsed)) return parsed;
    } catch {}
  }
  return null;
}

function withAiWarning<T extends Record<string, unknown>>(result: WorkerResult<T>, warning: string): WorkerResult<T> {
  return {
    ...result,
    warnings: [...(result.warnings ?? []), warning],
  };
}
