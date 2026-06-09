export type AIReviewBackendName = "external" | "local_rules";
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
export declare function resolveBackendName(value?: string): AIReviewBackendName;
export declare function buildBackend(name: AIReviewBackendName, options: {
    explicit?: AIReviewBackend;
    externalCommand?: string;
}): AIReviewBackend | undefined;
