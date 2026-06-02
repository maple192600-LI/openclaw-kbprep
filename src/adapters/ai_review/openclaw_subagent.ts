/**
 * OpenClaw subagent backend: calls the OpenClaw subagent runtime to run
 * an LLM that reviews batches. This is the legacy default; preserved for
 * backward compatibility with existing OpenClaw users.
 *
 * This module owns the ONLY `import "openclaw/plugin-sdk/..."` reference in
 * the AI Review layer. All other backends and the rest of the pipeline are
 * host-agnostic.
 */
import { readFile } from "node:fs/promises";
import type {
  AIReviewBackend,
  AIReviewBatch,
  AIReviewContext,
  AIReviewResponse,
  ReviewableResult,
} from "./backend.js";

type OpenClawSubagentApi = {
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

export interface OpenClawBackendOptions {
  api: { runtime?: { subagent?: OpenClawSubagentApi } };
  toolCallId: string;
  signal?: AbortSignal;
  timeoutMs: number;
  provider?: string;
  model?: string;
}

export class OpenClawSubagentBackend implements AIReviewBackend {
  readonly name = "openclaw" as const;

  constructor(private readonly opts: OpenClawBackendOptions) {}

  async isAvailable(): Promise<{ available: boolean; reason?: string }> {
    if (!this.opts.api.runtime?.subagent) {
      return {
        available: false,
        reason:
          "OpenClaw subagent API is not present in this host. " +
          "If you are running kbprep outside OpenClaw, use the 'claude_code' or 'codex' backend instead.",
      };
    }
    return { available: true };
  }

  async reviewBatch(batch: AIReviewBatch, systemPrompt: string): Promise<AIReviewResponse> {
    const subagent = this.opts.api.runtime?.subagent;
    if (!subagent) {
      return { patches: [], notes: ["openclaw subagent unavailable"] };
    }

    const sessionKey = `kbprep-ai-review-${this.opts.toolCallId}-${batch.number}`;
    try {
      const run = await subagent.run({
        sessionKey,
        message: batch.content,
        provider: this.opts.provider,
        model: this.opts.model,
        extraSystemPrompt: systemPrompt,
        lightContext: true,
        deliver: false,
        idempotencyKey: sessionKey,
      });
      const done = await subagent.waitForRun({ runId: run.runId, timeoutMs: this.opts.timeoutMs });
      if (done.status !== "completed") {
        return { patches: [], notes: [`openclaw subagent run did not complete: ${done.error ?? done.status}`] };
      }
      const messages = (await subagent.getSessionMessages({ sessionKey, limit: 4 })).messages;
      const lastText = extractLastAssistantText(messages);
      const patches = parseFirstJsonArray(lastText) ?? [];
      return { patches, notes: [`openclaw backend produced ${patches.length} patch ops`] };
    } catch (err) {
      return { patches: [], notes: [`openclaw backend error: ${String(err)}`] };
    }
  }
}

function extractLastAssistantText(messages: unknown[]): string {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const m = messages[i] as Record<string, unknown>;
    if (m.role !== "assistant") continue;
    const content = m.content;
    if (typeof content === "string") return content;
    if (Array.isArray(content)) {
      return content
        .map((c) => (typeof c === "object" && c && (c as Record<string, unknown>).text))
        .filter((s): s is string => typeof s === "string")
        .join("\n");
    }
  }
  return "";
}

function parseFirstJsonArray(text: string): Array<Record<string, unknown>> | null {
  const fenced = text.match(/```(?:json)?\s*([\s\S]*?)```/i);
  const candidates = fenced ? [fenced[1], text] : [text];
  for (const candidate of candidates) {
    const start = candidate.indexOf("[");
    const end = candidate.lastIndexOf("]");
    if (start < 0 || end <= start) continue;
    try {
      const parsed = JSON.parse(candidate.slice(start, end + 1));
      if (Array.isArray(parsed)) return parsed as Array<Record<string, unknown>>;
    } catch {
      /* try next candidate */
    }
  }
  return null;
}

export async function readReviewPack(reviewPackPath: string): Promise<string> {
  return readFile(reviewPackPath, "utf-8");
}
