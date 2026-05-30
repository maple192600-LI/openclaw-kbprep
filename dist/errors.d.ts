/**
 * KBPrep v4 error codes and error types.
 * Unified error codes from the v4 fix plan.
 */
export declare const KBPREP_ERROR_CODES: readonly ["E_INPUT_NOT_FOUND", "E_UNSUPPORTED_TYPE", "E_ENV_MISSING", "E_PYTHON_MISSING", "E_UV_MISSING", "E_MINERU_NOT_FOUND", "E_DISK_SPACE_LOW", "E_CONVERT_FAILED", "E_CONVERT_OUTPUT_MISSING", "E_TEXT_LAYER_GARBLED", "E_OCR_LOW_QUALITY", "E_NORMALIZE_FAILED", "E_BLOCKIFY_FAILED", "E_CLEAN_RULE_FAILED", "E_IMAGE_CLASSIFY_FAILED", "E_REVIEW_PACK_FAILED", "E_REVIEW_PATCH_INVALID", "E_SPLIT_FAILED", "E_QA_FAILED", "E_TIMEOUT", "KBPREP_INVALID_INPUT", "KBPREP_WORKER_TIMEOUT", "KBPREP_WORKER_BAD_JSON", "KBPREP_CANCELLED", "KBPREP_INTERNAL"];
export declare const KBPREP_WARNING_CODES: readonly ["W_LLM_REVIEW_SKIPPED", "W_GENERIC_SPLITTER_USED", "W_OCR_AI_CONFUSION", "W_IMAGE_CLASS_UNKNOWN", "W_LOW_COVERAGE", "W_MARKETING_BLOCK_MOVED_TO_EVIDENCE", "W_PDF_TEXT_LAYER_UNTRUSTED", "W_FORCE_OCR_RECOMMENDED"];
export type KBPrepErrorCode = (typeof KBPREP_ERROR_CODES)[number];
export type KBPrepWarningCode = (typeof KBPREP_WARNING_CODES)[number];
export interface KBPrepError {
    code: KBPrepErrorCode;
    message: string;
    recoverable: boolean;
    suggested_action: string;
    details: Record<string, unknown>;
}
export declare class KBPrepException extends Error {
    readonly kbprepError: KBPrepError;
    constructor(err: KBPrepError);
}
export declare function makeError(code: KBPrepErrorCode, message: string, opts?: {
    recoverable?: boolean;
    suggested_action?: string;
    details?: Record<string, unknown>;
}): KBPrepError;
