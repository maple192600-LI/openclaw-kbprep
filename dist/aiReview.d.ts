import { type WorkerResult } from "./worker.js";
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
type AiReviewBackend = {
    review: (params: {
        sessionKey: string;
        message: string;
        systemPrompt: string;
        provider?: string;
        model?: string;
        timeoutMs?: number;
        idempotencyKey?: string;
    }) => Promise<{
        messages: unknown[];
        warning?: string;
    }>;
};
type AiReviewContext = {
    api: {
        runtime?: {
            aiReviewBackend?: AiReviewBackend;
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
                }) => Promise<{
                    runId: string;
                }>;
                waitForRun: (params: {
                    runId: string;
                    timeoutMs?: number;
                }) => Promise<{
                    status: string;
                    error?: string;
                }>;
                getSessionMessages: (params: {
                    sessionKey: string;
                    limit?: number;
                }) => Promise<{
                    messages: unknown[];
                }>;
            };
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
