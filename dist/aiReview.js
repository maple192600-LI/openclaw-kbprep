import { readFile } from "node:fs/promises";
import { callWorker } from "./worker.js";
const REVIEW_PACK_MAX_CHARS = 80_000;
const REVIEW_PACK_BATCH_TARGET_CHARS = 60_000;
export async function maybeRunAiReview(result, params, config, context, opts) {
    if (params.mode !== "ai_review" || !result.ok) {
        return result;
    }
    const subagent = context.api.runtime?.subagent;
    const runDir = String(result.data?.run_dir ?? "");
    const reviewPackPath = String(result.data?.outputs?.review_pack ?? "");
    if (!subagent || !runDir || !reviewPackPath) {
        return withAiWarning(result, "W_LLM_REVIEW_SKIPPED: AI review unavailable or review_pack missing.");
    }
    let reviewPack = "";
    try {
        reviewPack = await readFile(reviewPackPath, "utf-8");
    }
    catch (err) {
        return withAiWarning(result, `W_LLM_REVIEW_SKIPPED: could not read review_pack.json (${String(err)}).`);
    }
    const batches = buildReviewBatches(reviewPack);
    if (!batches.length) {
        return withAiWarning(result, "W_LLM_REVIEW_SKIPPED: review_pack.json could not be split into review batches.");
    }
    const combinedPatch = [];
    const aiWarnings = [];
    for (const [index, batch] of batches.entries()) {
        const sessionKey = `kbprep-review:${context.toolCallId}:${Date.now()}:${index + 1}`;
        const message = buildReviewPrompt(batch, index + 1, batches.length);
        const run = await subagent.run({
            sessionKey,
            message,
            provider: params.ai_review_provider ?? config.ai_review_provider,
            model: params.ai_review_model ?? config.ai_review_model,
            extraSystemPrompt: AI_REVIEW_SYSTEM_PROMPT,
            lane: "kbprep-review",
            lightContext: true,
            deliver: false,
            idempotencyKey: `${context.toolCallId}:${index + 1}`,
        });
        const waited = await subagent.waitForRun({ runId: run.runId, timeoutMs: opts.timeoutMs });
        if (waited.status !== "ok") {
            aiWarnings.push(`W_LLM_REVIEW_BATCH_SKIPPED: batch ${index + 1}/${batches.length} ${waited.status}${waited.error ? ` (${waited.error})` : ""}.`);
            continue;
        }
        const messages = await subagent.getSessionMessages({ sessionKey, limit: 20 });
        const patch = extractJsonPatch(messages.messages);
        if (!patch) {
            aiWarnings.push(`W_LLM_REVIEW_BATCH_SKIPPED: batch ${index + 1}/${batches.length} did not return a JSON Patch array.`);
            continue;
        }
        combinedPatch.push(...patch);
    }
    if (combinedPatch.length === 0 && aiWarnings.length === batches.length) {
        return {
            ...result,
            warnings: [...(result.warnings ?? []), ...aiWarnings, "W_LLM_REVIEW_SKIPPED: all AI review batches failed."],
        };
    }
    const applied = await callWorker("apply_review", {
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
    const originalData = (result.data ?? {});
    const appliedData = (applied.data ?? {});
    const originalOutputs = (originalData.outputs ?? {});
    const updatedOutputs = (appliedData.updated_outputs ?? {});
    return {
        ...applied,
        data: {
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
        },
        warnings: [...(result.warnings ?? []), ...aiWarnings, ...(applied.warnings ?? [])],
    };
}
function buildReviewPrompt(reviewPack, batchNumber = 1, batchCount = 1) {
    return [
        `Review this kbprep review_pack.json batch ${batchNumber}/${batchCount}.`,
        "Return ONLY an RFC 6902 JSON Patch array.",
        "Allowed fields are status, risk_tags, reason, confidence.",
        "Allowed statuses are keep, discard, evidence, review.",
        "Never rewrite text. Never summarize. Never discard steps, prompts, code, tables, tool names, numbers, parameters, links, or concrete examples.",
        "If context is insufficient, set status to review.",
        "",
        reviewPack,
    ].join("\n");
}
function buildReviewBatches(reviewPack) {
    if (reviewPack.length <= REVIEW_PACK_MAX_CHARS)
        return [reviewPack];
    let parsed;
    try {
        parsed = JSON.parse(reviewPack);
    }
    catch {
        return [];
    }
    if (!parsed || typeof parsed !== "object")
        return [];
    const pack = parsed;
    const blocks = Array.isArray(pack.blocks) ? pack.blocks : [];
    if (!blocks.length)
        return [JSON.stringify({ ...pack, blocks: [] }, null, 2)];
    const batches = [];
    let current = [];
    for (const block of blocks) {
        const candidate = serializeReviewBatch(pack, [...current, block]);
        if (candidate.length > REVIEW_PACK_BATCH_TARGET_CHARS && current.length > 0) {
            batches.push(serializeReviewBatch(pack, current));
            current = [block];
        }
        else {
            current.push(block);
        }
    }
    if (current.length)
        batches.push(serializeReviewBatch(pack, current));
    return batches;
}
function serializeReviewBatch(pack, blocks) {
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
function extractJsonPatch(messages) {
    for (const message of [...messages].reverse()) {
        const text = stringifyMessage(message);
        const parsed = parseFirstJsonArray(text);
        if (parsed && parsed.every((item) => typeof item === "object" && item !== null && "op" in item && "path" in item)) {
            return parsed;
        }
    }
    return null;
}
function stringifyMessage(message) {
    if (typeof message === "string")
        return message;
    if (message && typeof message === "object") {
        const record = message;
        for (const key of ["content", "text", "message", "body"]) {
            const value = record[key];
            if (typeof value === "string")
                return value;
        }
    }
    return JSON.stringify(message);
}
function parseFirstJsonArray(text) {
    const fenced = text.match(/```(?:json)?\s*([\s\S]*?)```/i);
    const candidates = fenced ? [fenced[1], text] : [text];
    for (const candidate of candidates) {
        const start = candidate.indexOf("[");
        const end = candidate.lastIndexOf("]");
        if (start < 0 || end <= start)
            continue;
        try {
            const parsed = JSON.parse(candidate.slice(start, end + 1));
            if (Array.isArray(parsed))
                return parsed;
        }
        catch { }
    }
    return null;
}
function withAiWarning(result, warning) {
    return {
        ...result,
        warnings: [...(result.warnings ?? []), warning],
    };
}
