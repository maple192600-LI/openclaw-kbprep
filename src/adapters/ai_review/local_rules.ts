/**
 * Local rules backend: no external AI call. Returns an empty patch with
 * a note explaining that AI review is disabled in this configuration.
 *
 * This is the safe default. The Python worker still produces a
 * `review_pack.json`, but no AI action is taken; a human (or the user)
 * can still apply edits via `kbprep_apply_review` with hand-written patches.
 */
import type { AIReviewBackend, AIReviewBatch, AIReviewResponse } from "./backend.js";

export class LocalRulesBackend implements AIReviewBackend {
  readonly name = "local_rules" as const;

  async isAvailable(): Promise<{ available: boolean }> {
    return { available: true };
  }

  async reviewBatch(_batch: AIReviewBatch, _systemPrompt: string): Promise<AIReviewResponse> {
    return {
      patches: [],
      notes: [
        "ai_review backend=local_rules: no AI call performed. " +
          "Apply edits manually or switch backend to 'openclaw' | 'claude_code' | 'codex'."
      ],
    };
  }
}
