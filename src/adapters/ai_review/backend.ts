/**
 * AI Review backend abstraction.
 *
 * kbprep's AI review pass reads a `review_pack.json` file (produced by the
 * Python worker's `prepare` command with `mode=rules_plus_review_pack` or
 * `mode=ai_review`) and emits a JSON Patch 1.0 patch ops array. The actual
 * AI call is host-specific; this interface lets the rest of the pipeline
 * be host-agnostic.
 *
 * Available backends:
 *   - `local_rules`:    No external AI call. Returns an empty patch. Deterministic.
 *   - `openclaw`:       OpenClaw subagent (legacy default — see openclaw_subagent.ts).
 *   - `claude_code`:    Shell out to the `claude` CLI (Claude Code).
 *   - `codex`:          Shell out to the `codex` CLI (OpenAI Codex CLI).
 *
 * Hosts pick the backend via the `ai_review_backend` config field.
 * Default if not set: `local_rules` (safe offline default; the user must
 * explicitly opt into an AI backend to get one).
 */
import type { WorkerResult } from "../../worker.js";

export type ReviewBackendName = "local_rules" | "openclaw" | "claude_code" | "codex";

export interface AIReviewBatch {
  /** 1-indexed batch number (for diagnostics). */
  number: number;
  /** Total number of batches. */
  of: number;
  /** Plain-text review pack content for this batch. */
  content: string;
  /** Maximum characters allowed in a single response (defensive cap). */
  maxResponseChars?: number;
}

export interface AIReviewResponse {
  /** JSON Patch 1.0 ops; may be empty if the AI produced no actions. */
  patches: Array<Record<string, unknown>>;
  /** Human-readable notes from the AI (for audit). */
  notes: string[];
  /** Tokens used, if reported by the backend. */
  tokensUsed?: number;
}

export interface AIReviewBackend {
  readonly name: ReviewBackendName;
  /** True if this backend is usable in the current environment. */
  isAvailable(): Promise<{ available: boolean; reason?: string }>;
  /**
   * Run a single review batch.
   * Implementations should never throw on AI-side failures; instead, return
   * `{patches: [], notes: [errorMessage]}` and let the pipeline record a
   * `W_LLM_REVIEW_SKIPPED` warning.
   */
  reviewBatch(batch: AIReviewBatch, systemPrompt: string): Promise<AIReviewResponse>;
}

/**
 * WorkerResult shape that AI review is meant to operate on. We keep the
 * reference loose so this module can be imported by hosts that don't have
 * the full WorkerResult type in their typeshed.
 */
export type ReviewableResult = WorkerResult<Record<string, unknown>>;

export interface AIReviewContext {
  /** Path to the review_pack.json produced by Python worker. */
  reviewPackPath: string;
  /** Run directory (for emitting side files like `ai_review_log.json`). */
  runDir: string;
  /** Optional override; defaults to env KBPREP_AI_REVIEW_BACKEND or "local_rules". */
  backendName?: ReviewBackendName;
  /** Optional provider/model (forwarded to backends that take one). */
  provider?: string;
  model?: string;
}
