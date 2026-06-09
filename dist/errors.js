import { KBPREP_ERROR_CODES, KBPREP_WARNING_CODES, } from "./errorCodes.js";
export { KBPREP_ERROR_CODES, KBPREP_WARNING_CODES, };
export class KBPrepException extends Error {
    kbprepError;
    constructor(err) {
        super(err.message);
        this.name = "KBPrepException";
        this.kbprepError = err;
    }
}
export function makeError(code, message, opts = {}) {
    return {
        code,
        message,
        recoverable: opts.recoverable ?? true,
        suggested_action: opts.suggested_action ?? "Check input and retry.",
        details: opts.details ?? {},
    };
}
