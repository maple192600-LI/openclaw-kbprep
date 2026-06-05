import { type AIReviewBackend, type OpenClawSubagentRuntime } from "./adapters/ai_review/index.js";
import { type WorkerResult } from "./worker.js";
type PluginConfig = {
    ai_review_backend?: "openclaw" | "local_rules" | "claude_code" | "codex";
    ai_review_provider?: string;
    ai_review_model?: string;
    device_override?: "cuda" | "cpu";
    max_cpu_threads?: number;
    min_free_memory_gb?: number;
};
type AiReviewParams = {
    mode?: "rules_only" | "rules_plus_review_pack" | "ai_review";
    ai_review_backend?: "openclaw" | "local_rules" | "claude_code" | "codex";
    ai_review_provider?: string;
    ai_review_model?: string;
};
type AiReviewContext = {
    api: {
        runtime?: {
            aiReviewBackend?: AIReviewBackend;
            subagent?: OpenClawSubagentRuntime;
        };
    };
    toolCallId: string;
    signal?: AbortSignal;
};
export declare function maybeRunAiReview<T extends Record<string, unknown>>(result: WorkerResult<T>, params: AiReviewParams, config: PluginConfig, context: AiReviewContext, opts: {
    pythonPath: string;
    timeoutMs: number;
    workerConfig: Record<string, unknown>;
}): Promise<WorkerResult<T>>;
export {};
