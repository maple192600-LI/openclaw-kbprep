"""Dictionary promotion history summaries and resolution checks."""

from datetime import datetime, timezone
from pathlib import Path

from ..envelope import fail, ok
from ..typing_helpers import as_int, as_object
from .inputs import _target_rules_dir
from .jsonl_store import _append_jsonl_locked, _read_jsonl
from .patterns import _optional_string, _string_list
from .rerun_verification import _dedupe_paths_local, _rerun_representative_source

def _promotion_history_risk(*, target_rules_dir: Path, document_type: str) -> dict:
    history_path = target_rules_dir / "promotion_history.jsonl"
    if not history_path.exists():
        return {
            "status": "clear",
            "history_path": str(history_path),
            "reason": "No promotion history found for this rules directory.",
        }
    entries = [
        item for item in _read_jsonl(history_path)
        if item.get("schema") in {"kbprep.dictionary_promotion_history.v1", "kbprep.dictionary_promotion_resolution.v1"}
        and item.get("document_type") == document_type
    ]
    if not entries:
        return {
            "status": "clear",
            "history_path": str(history_path),
            "reason": f"No promotion history found for document_type: {document_type}.",
        }
    summary = _promotion_history_document_summary(document_type, entries)
    if summary.get("failed_promotions", 0):
        return {
            "status": "blocked",
            "history_path": str(history_path),
            "summary": summary,
            "reason": "Failed promotion history exists for this document type.",
        }
    if summary.get("unverified_promotions", 0):
        return {
            "status": "warn",
            "history_path": str(history_path),
            "summary": summary,
            "reason": "Unverified promotion history exists for this document type.",
        }
    return {
        "status": "clear",
        "history_path": str(history_path),
        "summary": summary,
    }

def _append_promotion_history(
    *,
    document_type: str,
    target_rules_dir: Path,
    target_path: Path,
    backup_path: Path | None,
    promoted_rules: list[dict],
    skipped_duplicates: int,
    suggestions_path: Path,
    regression_verification: dict,
) -> dict:
    history_path = target_rules_dir / "promotion_history.jsonl"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "schema": "kbprep.dictionary_promotion_history.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "document_type": document_type,
        "target_path": str(target_path),
        "backup_path": str(backup_path) if backup_path else None,
        "source_suggestions_path": str(suggestions_path),
        "promoted_count": len(promoted_rules),
        "skipped_duplicates": skipped_duplicates,
        "promoted_rule_ids": [
            str(rule.get("id"))
            for rule in promoted_rules
            if rule.get("id")
        ],
        "regression_verification": regression_verification,
    }
    _append_jsonl_locked(history_path, entry)
    return {"path": history_path, "entry": entry}

def _summarize_promotion_history(data: dict) -> None:
    target_rules_dir = _target_rules_dir(data)
    history_path = Path(
        _optional_string(data.get("promotion_history_file")) or str(target_rules_dir / "promotion_history.jsonl")
    ).expanduser().resolve()
    document_type_filter = _optional_string(data.get("document_type"))
    if not history_path.exists():
        ok(data={
            "summary": {
                "schema": "kbprep.dictionary_promotion_history_summary.v1",
                "history_path": str(history_path),
                "total_promotions": 0,
                "document_types": [],
                "recommendation": "No promotion history found. Promote only after review and rerun representative sources when possible.",
            },
        })
        return

    entries = [
        item for item in _read_jsonl(history_path)
        if item.get("schema") in {"kbprep.dictionary_promotion_history.v1", "kbprep.dictionary_promotion_resolution.v1"}
    ]
    if document_type_filter:
        entries = [
            item for item in entries
            if item.get("document_type") == document_type_filter
        ]

    grouped: dict[str, list[dict]] = {}
    for entry in entries:
        document_type = _optional_string(entry.get("document_type")) or "unknown"
        grouped.setdefault(document_type, []).append(entry)

    document_types = [
        _promotion_history_document_summary(document_type, items)
        for document_type, items in sorted(grouped.items())
    ]
    ok(data={
        "summary": {
            "schema": "kbprep.dictionary_promotion_history_summary.v1",
            "history_path": str(history_path),
            "document_type_filter": document_type_filter,
            "total_promotions": len(entries),
            "document_types": document_types,
            "recommendation": _overall_history_recommendation(document_types),
        },
    })

def _promotion_history_document_summary(document_type: str, entries: list[dict]) -> dict:
    sorted_entries = sorted(entries, key=lambda item: str(item.get("created_at") or ""))
    passed = 0
    failed = 0
    resolved_failed = 0
    unverified = 0
    total_samples = 0
    passed_samples = 0
    failed_samples = 0
    promoted_rules = 0
    skipped_duplicates = 0
    failure_reasons: dict[str, int] = {}

    for entry in sorted_entries:
        schema = entry.get("schema")
        if schema == "kbprep.dictionary_promotion_resolution.v1":
            verification = entry.get("regression_verification")
            verification = verification if isinstance(verification, dict) else {}
            if verification.get("status") == "passed":
                resolved_failed += _positive_int_or_zero(entry.get("resolved_failed_promotions")) or 1
                total_samples += _positive_int_or_zero(verification.get("sample_count"))
                passed_samples += _positive_int_or_zero(verification.get("passed_count"))
                failed_samples += _positive_int_or_zero(verification.get("failed_count"))
            else:
                unverified += 1
            continue

        promoted_rules += _positive_int_or_zero(entry.get("promoted_count"))
        skipped_duplicates += _positive_int_or_zero(entry.get("skipped_duplicates"))
        verification = entry.get("regression_verification")
        verification = verification if isinstance(verification, dict) else {}
        status = _optional_string(verification.get("status")) or "unknown"
        if status == "passed":
            passed += 1
        elif status == "failed":
            failed += 1
        else:
            unverified += 1
        total_samples += _positive_int_or_zero(verification.get("sample_count"))
        passed_samples += _positive_int_or_zero(verification.get("passed_count"))
        failed_samples += _positive_int_or_zero(verification.get("failed_count"))
        for reason in _promotion_failure_reasons(verification):
            failure_reasons[reason] = failure_reasons.get(reason, 0) + 1

    latest = sorted_entries[-1] if sorted_entries else {}
    if latest.get("schema") == "kbprep.dictionary_promotion_resolution.v1":
        latest_resolution = as_object(latest.get("regression_verification"))
        latest_status = "resolved" if latest_resolution.get("status") == "passed" else "resolution_failed"
    else:
        latest_verification = as_object(latest.get("regression_verification"))
        latest_status = _optional_string(latest_verification.get("status")) or "unknown"
    unresolved_failed = max(0, failed - resolved_failed)
    return {
        "document_type": document_type,
        "promotions": len(sorted_entries),
        "passed_promotions": passed,
        "failed_promotions": unresolved_failed,
        "raw_failed_promotions": failed,
        "resolved_failed_promotions": resolved_failed,
        "unverified_promotions": unverified,
        "total_promoted_rules": promoted_rules,
        "skipped_duplicates": skipped_duplicates,
        "total_samples": total_samples,
        "passed_samples": passed_samples,
        "failed_samples": failed_samples,
        "latest_status": latest_status,
        "latest_created_at": latest.get("created_at"),
        "failure_reasons": [
            {"reason": reason, "count": count}
            for reason, count in sorted(failure_reasons.items())
        ],
        "recommendation": _document_history_recommendation(
            failed_promotions=unresolved_failed,
            unverified_promotions=unverified,
            latest_status=latest_status,
        ),
    }

def _resolve_promotion_failures(data: dict) -> None:
    if data.get("confirm_failure_resolved") is not True:
        fail(
            "E_CONFIRMATION_REQUIRED",
            "confirm_failure_resolved must be true before failed promotion history can be marked resolved.",
            recoverable=True,
            suggested_action="Rerun representative samples, inspect quality_report.json and cleaned.md, then retry with confirm_failure_resolved=true.",
        )

    document_type = _optional_string(data.get("document_type"))
    if not document_type or document_type == "unknown":
        fail("E_INVALID_INPUT", "document_type is required and cannot be unknown")
        raise AssertionError("unreachable")
    target_rules_dir = _target_rules_dir(data)
    history_path = target_rules_dir / "promotion_history.jsonl"
    if not history_path.exists():
        fail("E_INPUT_NOT_FOUND", f"promotion_history.jsonl does not exist: {history_path}")

    existing = [
        item for item in _read_jsonl(history_path)
        if item.get("schema") in {"kbprep.dictionary_promotion_history.v1", "kbprep.dictionary_promotion_resolution.v1"}
        and item.get("document_type") == document_type
    ]
    summary = _promotion_history_document_summary(document_type, existing)
    unresolved_failed = _positive_int_or_zero(summary.get("failed_promotions"))
    if unresolved_failed == 0:
        ok(data={
            "resolution": {
                "schema": "kbprep.dictionary_promotion_resolution.v1",
                "document_type": document_type,
                "status": "not_needed",
                "resolved_failed_promotions": 0,
                "history_path": str(history_path),
                "summary": summary,
            },
        })
        return

    run_dirs = [
        Path(value).expanduser().resolve()
        for value in _string_list(data.get("representative_run_dirs"))
    ]
    if not run_dirs:
        fail(
            "E_INPUT_NOT_FOUND",
            "representative_run_dirs is required to resolve failed promotion history.",
            recoverable=True,
            suggested_action="Pass at least one representative_run_dir from the failed or fixed document-type samples.",
        )

    samples = [
        _rerun_representative_source(
            run_dir=run_dir,
            target_rules_dir=target_rules_dir,
            promoted_rules=[],
        )
        for run_dir in _dedupe_paths_local(run_dirs)
    ]
    passed = [sample for sample in samples if sample.get("ok")]
    verification = {
        "status": "passed" if len(passed) == len(samples) else "failed",
        "ok": len(passed) == len(samples),
        "sample_count": len(samples),
        "passed_count": len(passed),
        "failed_count": len(samples) - len(passed),
        "samples": samples,
    }
    if verification["status"] != "passed":
        fail(
            "E_PROMOTION_RESOLUTION_FAILED",
            "Representative reruns still fail; failed promotion history remains unresolved.",
            details={"regression_verification": verification, "summary": summary},
            recoverable=True,
            suggested_action="Inspect failed sample quality_report.json and cleaned.md before marking this promotion history resolved.",
        )

    entry = {
        "schema": "kbprep.dictionary_promotion_resolution.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "document_type": document_type,
        "resolved_failed_promotions": unresolved_failed,
        "history_path": str(history_path),
        "regression_verification": verification,
    }
    _append_jsonl_locked(history_path, entry)
    updated_entries = [*existing, entry]
    ok(data={
        "resolution": entry,
        "summary": _promotion_history_document_summary(document_type, updated_entries),
    })

def _promotion_failure_reasons(verification: dict) -> list[str]:
    reasons = []
    if _optional_string(verification.get("reason")):
        reasons.append(str(verification.get("reason")))
    samples = verification.get("samples")
    if isinstance(samples, list):
        for sample in samples:
            if not isinstance(sample, dict) or sample.get("ok"):
                continue
            if _optional_string(sample.get("reason")):
                reasons.append(str(sample.get("reason")))
            worker_error = sample.get("worker_error")
            if isinstance(worker_error, dict) and _optional_string(worker_error.get("code")):
                reasons.append(str(worker_error.get("code")))
            effects = sample.get("rule_effects")
            if isinstance(effects, list):
                for effect in effects:
                    if isinstance(effect, dict) and effect.get("ok") is False and _optional_string(effect.get("effect")):
                        reasons.append(str(effect.get("effect")))
    return reasons

def _document_history_recommendation(*, failed_promotions: int, unverified_promotions: int, latest_status: str) -> str:
    if failed_promotions or latest_status == "failed":
        return "Stop promoting more rules for this document type until failed regression samples are reviewed."
    if unverified_promotions or latest_status in {"not_requested", "unavailable", "unknown"}:
        return "Run regression verification before accepting more dictionary changes for this document type."
    return "Promotion history is currently passing; continue requiring review and representative reruns."

def _overall_history_recommendation(document_types: list[dict]) -> str:
    if any(item.get("failed_promotions", 0) for item in document_types):
        return "At least one document type has failed promotions; review failures before adding more rules."
    if any(item.get("unverified_promotions", 0) for item in document_types):
        return "Some promotions are unverified; run representative regression before relying on those dictionaries."
    if document_types:
        return "Promotion history is passing so far; keep using confirmation and regression checks."
    return "No promotion history found."

def _positive_int_or_zero(value: object) -> int:
    return max(0, as_int(value, default=0))
