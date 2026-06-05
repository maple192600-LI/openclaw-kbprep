export type AIReviewBackendName = "openclaw" | "local_rules" | "claude_code" | "codex";
export type AIReviewBackend = {
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
export type OpenClawSubagentRuntime = {
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
export declare function resolveBackendName(value?: string): AIReviewBackendName;
export declare function buildBackend(name: AIReviewBackendName, options: {
    explicit?: AIReviewBackend;
    openclawSubagent?: OpenClawSubagentRuntime;
}): AIReviewBackend | undefined;
