import { KBPREP_ERROR_CODES, KBPREP_WARNING_CODES, type KBPrepErrorCode, type KBPrepWarningCode } from "./errorCodes.js";
export { KBPREP_ERROR_CODES, KBPREP_WARNING_CODES, type KBPrepErrorCode, type KBPrepWarningCode, };
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
