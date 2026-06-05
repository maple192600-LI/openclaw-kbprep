export declare const AI_REVIEW_MAX_ATTEMPTS = 2;
export declare const AI_REVIEW_SYSTEM_PROMPT: string;
export declare function buildReviewPrompt(reviewPack: string, batchNumber?: number, batchCount?: number, attempt?: number): string;
export declare function buildReviewBatches(reviewPack: string): string[];
export declare function serializeReviewBatch(pack: Record<string, unknown>, blocks: unknown[]): string;
export declare function extractJsonPatch(messages: unknown[]): unknown[] | null;
export declare function validateAiReviewPatch(patch: unknown[]): {
    valid: unknown[];
    rejected: string[];
};
export declare function formatRejectedPatchWarning(batchNumber: number, batchCount: number, attempt: number, rejected: string[]): string;
