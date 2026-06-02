/**
 * KBPrep error and warning codes.
 *
 * Naming convention: `KBPREP_E_*` for errors, `KBPREP_W_*` for warnings.
 * Legacy `E_*` and `W_*` codes are kept as aliases (mapped to the new
 * prefixed codes) and will be removed in v1.0.0. New code should use the
 * `KBPREP_E_*` / `KBPREP_W_*` form directly.
 */

const LEGACY_ERROR_ALIASES: Record<string, string> = {
  E_INPUT_NOT_FOUND: "KBPREP_E_INPUT_NOT_FOUND",
  E_UNSUPPORTED_TYPE: "KBPREP_E_UNSUPPORTED_TYPE",
  E_ENV_MISSING: "KBPREP_E_ENV_MISSING",
  E_PYTHON_MISSING: "KBPREP_E_PYTHON_MISSING",
  E_UV_MISSING: "KBPREP_E_UV_MISSING",
  E_MINERU_NOT_FOUND: "KBPREP_E_MINERU_NOT_FOUND",
  E_DISK_SPACE_LOW: "KBPREP_E_DISK_SPACE_LOW",
  E_CONVERT_FAILED: "KBPREP_E_CONVERT_FAILED",
  E_CONVERT_OUTPUT_MISSING: "KBPREP_E_CONVERT_OUTPUT_MISSING",
  E_TEXT_LAYER_GARBLED: "KBPREP_E_TEXT_LAYER_GARBLED",
  E_OCR_LOW_QUALITY: "KBPREP_E_OCR_LOW_QUALITY",
  E_NORMALIZE_FAILED: "KBPREP_E_NORMALIZE_FAILED",
  E_BLOCKIFY_FAILED: "KBPREP_E_BLOCKIFY_FAILED",
  E_CLEAN_RULE_FAILED: "KBPREP_E_CLEAN_RULE_FAILED",
  E_IMAGE_CLASSIFY_FAILED: "KBPREP_E_IMAGE_CLASSIFY_FAILED",
  E_REVIEW_PACK_FAILED: "KBPREP_E_REVIEW_PACK_FAILED",
  E_REVIEW_PATCH_INVALID: "KBPREP_E_REVIEW_PATCH_INVALID",
  E_SPLIT_FAILED: "KBPREP_E_SPLIT_FAILED",
  E_QA_FAILED: "KBPREP_E_QA_FAILED",
  E_TIMEOUT: "KBPREP_E_TIMEOUT",
};

const LEGACY_WARNING_ALIASES: Record<string, string> = {
  W_LLM_REVIEW_SKIPPED: "KBPREP_W_LLM_REVIEW_SKIPPED",
  W_GENERIC_SPLITTER_USED: "KBPREP_W_GENERIC_SPLITTER_USED",
  W_OCR_AI_CONFUSION: "KBPREP_W_OCR_AI_CONFUSION",
  W_IMAGE_CLASS_UNKNOWN: "KBPREP_W_IMAGE_CLASS_UNKNOWN",
  W_LOW_COVERAGE: "KBPREP_W_LOW_COVERAGE",
  W_MARKETING_BLOCK_MOVED_TO_EVIDENCE: "KBPREP_W_MARKETING_BLOCK_MOVED_TO_EVIDENCE",
  W_PDF_TEXT_LAYER_UNTRUSTED: "KBPREP_W_PDF_TEXT_LAYER_UNTRUSTED",
  W_FORCE_OCR_RECOMMENDED: "KBPREP_W_FORCE_OCR_RECOMMENDED",
};

export const KBPREP_ERROR_CODES = [
  // ── Canonical (KBPREP_E_*) ─────────────────────────────────────
  "KBPREP_E_INPUT_NOT_FOUND",
  "KBPREP_E_UNSUPPORTED_TYPE",
  "KBPREP_E_ENV_MISSING",
  "KBPREP_E_PYTHON_MISSING",
  "KBPREP_E_UV_MISSING",
  "KBPREP_E_MINERU_NOT_FOUND",
  "KBPREP_E_DISK_SPACE_LOW",
  "KBPREP_E_CONVERT_FAILED",
  "KBPREP_E_CONVERT_INPUT_INVALID",
  "KBPREP_E_CONVERT_OUTPUT_MISSING",
  "KBPREP_E_TEXT_LAYER_GARBLED",
  "KBPREP_E_OCR_LOW_QUALITY",
  "KBPREP_E_NORMALIZE_FAILED",
  "KBPREP_E_BLOCKIFY_FAILED",
  "KBPREP_E_CLEAN_RULE_FAILED",
  "KBPREP_E_IMAGE_CLASSIFY_FAILED",
  "KBPREP_E_REVIEW_PACK_FAILED",
  "KBPREP_E_REVIEW_PATCH_INVALID",
  "KBPREP_E_SPLIT_FAILED",
  "KBPREP_E_QA_FAILED",
  "KBPREP_E_TIMEOUT",
  "KBPREP_E_AI_BACKEND_UNAVAILABLE",
  "KBPREP_E_AI_BACKEND_TIMEOUT",
  "KBPREP_E_AI_BACKEND_BAD_OUTPUT",
  // ── Generic (kept) ─────────────────────────────────────────────
  "KBPREP_INVALID_INPUT",
  "KBPREP_WORKER_TIMEOUT",
  "KBPREP_WORKER_BAD_JSON",
  "KBPREP_CANCELLED",
  "KBPREP_INTERNAL",
] as const;

export const KBPREP_WARNING_CODES = [
  // ── Canonical (KBPREP_W_*) ─────────────────────────────────────
  "KBPREP_W_LLM_REVIEW_SKIPPED",
  "KBPREP_W_LLM_REVIEW_BATCH_ATTEMPT_FAILED",
  "KBPREP_W_LLM_REVIEW_BATCH_SKIPPED",
  "KBPREP_W_LLM_REVIEW_PATCH_OP_REJECTED",
  "KBPREP_W_GENERIC_SPLITTER_USED",
  "KBPREP_W_OCR_AI_CONFUSION",
  "KBPREP_W_IMAGE_CLASS_UNKNOWN",
  "KBPREP_W_LOW_COVERAGE",
  "KBPREP_W_MARKETING_BLOCK_MOVED_TO_EVIDENCE",
  "KBPREP_W_PDF_TEXT_LAYER_UNTRUSTED",
  "KBPREP_W_PDF_TEXT_LAYER_FALLBACK_TO_OCR",
  "KBPREP_W_FORCE_OCR_RECOMMENDED",
] as const;

export type KBPrepErrorCode = (typeof KBPREP_ERROR_CODES)[number];
export type KBPrepWarningCode = (typeof KBPREP_WARNING_CODES)[number];

/** Normalize a legacy code (`E_FOO` / `W_FOO`) to the canonical `KBPREP_*` form. */
export function normalizeErrorCode(code: string): KBPrepErrorCode {
  if (KBPREP_ERROR_CODES.includes(code as KBPrepErrorCode)) {
    return code as KBPrepErrorCode;
  }
  const aliased = LEGACY_ERROR_ALIASES[code];
  if (aliased) return aliased as KBPrepErrorCode;
  return "KBPREP_INTERNAL";
}

export function normalizeWarningCode(code: string): KBPrepWarningCode {
  if (KBPREP_WARNING_CODES.includes(code as KBPrepWarningCode)) {
    return code as KBPrepWarningCode;
  }
  const aliased = LEGACY_WARNING_ALIASES[code];
  if (aliased) return aliased as KBPrepWarningCode;
  // Some legacy codes that don't map are still preserved verbatim (not in the strict list)
  // — return the original to avoid losing information.
  return code as KBPrepWarningCode;
}

export interface KBPrepError {
  code: KBPrepErrorCode;
  message: string;
  recoverable: boolean;
  suggested_action: string;
  details: Record<string, unknown>;
}

export class KBPrepException extends Error {
  public readonly kbprepError: KBPrepError;

  constructor(err: KBPrepError) {
    super(err.message);
    this.name = "KBPrepException";
    this.kbprepError = err;
  }
}

export function makeError(
  code: KBPrepErrorCode | string,
  message: string,
  opts: {
    recoverable?: boolean;
    suggested_action?: string;
    details?: Record<string, unknown>;
  } = {},
): KBPrepError {
  return {
    code: normalizeErrorCode(code),
    message,
    recoverable: opts.recoverable ?? true,
    suggested_action: opts.suggested_action ?? "",
    details: opts.details ?? {},
  };
}
