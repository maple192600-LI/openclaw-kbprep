/**
 * AI Review backend factory and shared types.
 */
import { LocalRulesBackend } from "./local_rules.js";
import type {
  AIReviewBackend,
  AIReviewBatch,
  AIReviewResponse,
  AIReviewContext,
  ReviewBackendName,
} from "./backend.js";

export type { AIReviewBackend, AIReviewBatch, AIReviewResponse, AIReviewContext, ReviewBackendName };
export { LocalRulesBackend } from "./local_rules.js";
export { OpenClawSubagentBackend, type OpenClawBackendOptions } from "./openclaw_subagent.js";
export { ClaudeCodeBackend, type ClaudeCodeBackendOptions } from "./claude_code.js";
export { CodexBackend, type CodexBackendOptions } from "./codex.js";

import { OpenClawSubagentBackend, type OpenClawBackendOptions } from "./openclaw_subagent.js";
import { ClaudeCodeBackend } from "./claude_code.js";
import { CodexBackend } from "./codex.js";

/**
 * Build a backend by name. The OpenClaw backend requires extra context
 * (api + toolCallId) which the host supplies; for non-OpenClaw backends
 * those are ignored.
 */
export function buildBackend(
  name: ReviewBackendName,
  opts: {
    openclaw?: OpenClawBackendOptions;
    claudeCode?: ConstructorParameters<typeof ClaudeCodeBackend>[0];
    codex?: ConstructorParameters<typeof CodexBackend>[0];
  } = {},
): AIReviewBackend {
  switch (name) {
    case "local_rules":
      return new LocalRulesBackend();
    case "openclaw": {
      if (!opts.openclaw) {
        throw new Error("openclaw backend requires `openclaw` options (api + toolCallId).");
      }
      return new OpenClawSubagentBackend(opts.openclaw);
    }
    case "claude_code":
      return new ClaudeCodeBackend(opts.claudeCode);
    case "codex":
      return new CodexBackend(opts.codex);
  }
}

export function resolveBackendName(override?: string): ReviewBackendName {
  if (
    override === "openclaw" ||
    override === "claude_code" ||
    override === "codex" ||
    override === "local_rules"
  ) {
    return override;
  }
  const fromEnv = process.env.KBPREP_AI_REVIEW_BACKEND;
  if (
    fromEnv === "openclaw" ||
    fromEnv === "claude_code" ||
    fromEnv === "codex" ||
    fromEnv === "local_rules"
  ) {
    return fromEnv;
  }
  return "local_rules";
}
