"""Promote reviewed feedback into document-type cleaning dictionaries."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from ..envelope import fail, ok
from ..rule_schema import validate_rule_file
from .inputs import _positive_int, _rules_dir, _target_rules_dir
from .jsonl_store import _read_jsonl
from .patterns import _dedupe_strings, _optional_string
from .proposals import _proposal_string_list
from .promotion_history import _append_promotion_history, _promotion_history_risk
from .rerun_verification import _rerun_after_dictionary_promotion

def _suggest_dictionary_updates(data: dict) -> None:
    rules_dir = _rules_dir(data)
    accepted = _read_jsonl(rules_dir / "accepted_rules.jsonl")
    rejected = _read_jsonl(rules_dir / "rejected_rules.jsonl")
    min_count = _positive_int(data.get("min_feedback_count"), 2)

    rejected_keys = {
        _feedback_cluster_key(item)
        for item in rejected
        if _feedback_cluster_key(item)
    }
    groups: dict[str, list[dict]] = {}
    for item in accepted:
        key = _feedback_cluster_key(item)
        if not key or key in rejected_keys:
            continue
        document_type = key[0]
        if item.get("action") != "discard":
            continue
        groups.setdefault(document_type, []).append(item)

    suggestions = []
    for document_type, items in sorted(groups.items()):
        deduped = _dedupe_feedback_items(items)
        if len(deduped) < min_count:
            continue
        suggestions.append(_dictionary_suggestion_for_document_type(document_type, deduped, rejected_keys))

    report = {
        "schema": "kbprep.dictionary_suggestions.v1",
        "rules_dir": str(rules_dir),
        "min_feedback_count": min_count,
        "suggestion_count": len(suggestions),
        "suggestions": suggestions,
    }
    suggestions_path = rules_dir / "dictionary_suggestions.jsonl"
    rules_dir.mkdir(parents=True, exist_ok=True)
    with suggestions_path.open("w", encoding="utf-8") as fh:
        for suggestion in suggestions:
            fh.write(json.dumps(suggestion, ensure_ascii=False) + "\n")

    ok(data={
        "suggestions": report,
        "suggestions_path": str(suggestions_path),
        "next_step": "Review dictionary_suggestions.jsonl before copying any proposal into rules/document_types/.",
    })

def _promote_dictionary_suggestion(data: dict) -> None:
    if data.get("confirm_dictionary_update") is not True:
        fail(
            "E_CONFIRMATION_REQUIRED",
            "confirm_dictionary_update must be true before a dictionary suggestion can be promoted.",
            recoverable=True,
            suggested_action="Review dictionary_suggestions.jsonl, then rerun with confirm_dictionary_update=true.",
        )

    document_type = _optional_string(data.get("document_type"))
    if not document_type or document_type == "unknown":
        fail("E_INVALID_INPUT", "document_type is required and cannot be unknown")

    rules_dir = _rules_dir(data)
    suggestions_path = Path(
        _optional_string(data.get("suggestions_file")) or str(rules_dir / "dictionary_suggestions.jsonl")
    ).expanduser().resolve()
    if not suggestions_path.exists():
        fail("E_INPUT_NOT_FOUND", f"dictionary suggestions file does not exist: {suggestions_path}")

    suggestions = _read_jsonl(suggestions_path)
    suggestion = next(
        (
            item for item in suggestions
            if item.get("schema") == "kbprep.dictionary_suggestion.v1"
            and item.get("document_type") == document_type
        ),
        None,
    )
    if not suggestion:
        fail("E_INPUT_NOT_FOUND", f"dictionary suggestion not found for document_type: {document_type}")

    validation = _validate_dictionary_suggestion(suggestion, str(suggestions_path))
    target_rules_dir = _target_rules_dir(data)
    history_risk = _promotion_history_risk(
        target_rules_dir=target_rules_dir,
        document_type=document_type,
    )
    if history_risk["status"] == "blocked" and data.get("allow_failed_promotion_history") is not True:
        fail(
            "E_PROMOTION_HISTORY_FAILED",
            "This document type has failed dictionary promotion history.",
            details=history_risk,
            recoverable=True,
            suggested_action="Review promotion_history.jsonl and failed regression samples, or rerun with allow_failed_promotion_history=true if the user explicitly accepts the risk.",
        )
    if history_risk["status"] == "blocked":
        history_risk = {**history_risk, "status": "override_used"}

    target_path = target_rules_dir / "document_types" / f"{document_type}.json"
    target_path.parent.mkdir(parents=True, exist_ok=True)

    rule_file = _load_or_create_document_type_rule_file(target_path, document_type)
    existing_rules = rule_file.setdefault("rules", [])
    if not isinstance(existing_rules, list):
        fail("E_INVALID_INPUT", f"{target_path}: rules must be a list")

    existing_keys = {
        (
            str(rule.get("type") or ""),
            str(rule.get("action") or ""),
            str(rule.get("match") or ""),
            str(rule.get("pattern") or ""),
        )
        for rule in existing_rules
        if isinstance(rule, dict)
    }
    promoted_rules = []
    for proposed in validation["proposed_rules"]:
        new_rule = _promoted_cleaning_rule(document_type, proposed)
        key = (
            new_rule["type"],
            new_rule["action"],
            new_rule["match"],
            new_rule["pattern"],
        )
        if key in existing_keys:
            continue
        existing_keys.add(key)
        existing_rules.append(new_rule)
        promoted_rules.append(new_rule)

    validate_rule_file(rule_file, str(target_path))
    backup_path = None
    if target_path.exists():
        backup_path = target_path.with_suffix(target_path.suffix + ".bak").resolve()
        backup_path.write_text(target_path.read_text(encoding="utf-8"), encoding="utf-8")
    target_path.write_text(json.dumps(rule_file, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    regression_verification = _rerun_after_dictionary_promotion(
        suggestion=suggestion,
        target_rules_dir=target_rules_dir,
        promoted_rules=promoted_rules,
        data=data,
    )
    promotion_history = _append_promotion_history(
        document_type=document_type,
        target_rules_dir=target_rules_dir,
        target_path=target_path,
        backup_path=backup_path,
        promoted_rules=promoted_rules,
        skipped_duplicates=len(validation["proposed_rules"]) - len(promoted_rules),
        suggestions_path=suggestions_path,
        regression_verification=regression_verification,
    )

    ok(data={
        "promoted": {
            "schema": "kbprep.dictionary_promotion.v1",
            "document_type": document_type,
            "target_path": str(target_path),
            "backup_path": str(backup_path) if backup_path else None,
            "promoted_count": len(promoted_rules),
            "skipped_duplicates": len(validation["proposed_rules"]) - len(promoted_rules),
            "promoted_rules": promoted_rules,
            "source_suggestions_path": str(suggestions_path),
            "regression_verification": regression_verification,
            "promotion_history_path": str(promotion_history["path"]),
            "promotion_history_entry": promotion_history["entry"],
            "history_risk": history_risk,
        },
        "next_step": "Run prepare on representative files for this document type and inspect quality_report.json before distributing the updated dictionary.",
    })

def _load_or_create_document_type_rule_file(path: Path, document_type: str) -> dict:
    if path.exists():
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        validate_rule_file(data, str(path))
        return data
    return {
        "schema": "kbprep.cleaning_rules.v1",
        "description": f"{document_type}-specific cleanup and protection vocabulary learned from confirmed feedback.",
        "rules": [],
        "keyword_sets": _empty_keyword_sets(),
    }

def _empty_keyword_sets() -> dict:
    return {
        "cta_keywords": [],
        "qr_image_markers": [],
        "image_qr_indicators": [],
        "image_marketing_indicators": [],
        "image_operation_indicators": [],
        "image_proof_indicators": [],
        "image_educational_heading_indicators": [],
        "tutorial_indicators": [],
        "knowledge_terms": [],
        "refund_patterns": [],
        "footer_patterns": [],
        "evidence_patterns": [],
        "marketing_wrapper_heading_terms": [],
        "marketing_wrapper_back_matter_terms": [],
        "marketing_wrapper_line_patterns": [],
        "business_method_context_terms": [],
        "transcript_filler_patterns": [],
        "protected_patterns": [],
        "feedback_protect_intent_terms": [],
        "feedback_discard_intent_terms": [],
    }

def _validate_dictionary_suggestion(suggestion: dict, source: str) -> dict:
    if suggestion.get("schema") != "kbprep.dictionary_suggestion.v1":
        fail("E_INVALID_INPUT", f"{source}: schema must be kbprep.dictionary_suggestion.v1")
    if suggestion.get("required_confirmation") is not True:
        fail("E_INVALID_INPUT", f"{source}: required_confirmation must be true")
    proposed_rules = suggestion.get("proposed_rules")
    if not isinstance(proposed_rules, list) or not proposed_rules:
        fail("E_INVALID_INPUT", f"{source}: proposed_rules must be a non-empty list")

    validated = []
    for idx, item in enumerate(proposed_rules):
        if not isinstance(item, dict):
            fail("E_INVALID_INPUT", f"{source}: proposed_rules[{idx}] must be an object")
        action = _optional_string(item.get("action"))
        match = _optional_string(item.get("match")) or "literal"
        pattern = _optional_string(item.get("pattern"))
        reason = _optional_string(item.get("reason")) or "learned from confirmed feedback"
        if action not in {"discard", "review", "protect"}:
            fail("E_INVALID_INPUT", f"{source}: proposed_rules[{idx}].action must be discard, review, or protect")
        if match not in {"literal", "regex"}:
            fail("E_INVALID_INPUT", f"{source}: proposed_rules[{idx}].match must be literal or regex")
        if not pattern:
            fail("E_INVALID_INPUT", f"{source}: proposed_rules[{idx}].pattern is required")
        if match == "regex":
            try:
                re.compile(pattern)
            except re.error as exc:
                fail("E_INVALID_INPUT", f"{source}: proposed_rules[{idx}].pattern is not a valid regex: {exc}")
        validated.append({
            "action": action,
            "match": match,
            "pattern": pattern,
            "reason": reason,
            "source_proposal_id": _optional_string(item.get("source_proposal_id")),
            "accepted_rule_id": _optional_string(item.get("accepted_rule_id")),
        })
    return {"proposed_rules": validated}

def _promoted_cleaning_rule(document_type: str, proposed: dict) -> dict:
    base_id = proposed.get("accepted_rule_id") or proposed.get("source_proposal_id") or proposed["pattern"]
    return {
        "id": _rule_id(f"learned-{document_type}-{base_id}"),
        "type": "promotional_line",
        "action": proposed["action"],
        "match": proposed["match"],
        "pattern": proposed["pattern"],
        "reason": proposed["reason"],
        "risk_tag": f"learned_feedback_{document_type}",
    }

def _rule_id(value: object) -> str:
    text = str(value or "rule").lower()
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", text, flags=re.UNICODE).strip("-")
    return text[:96] or f"rule-{uuid4().hex[:8]}"

def _feedback_cluster_key(item: dict) -> tuple[str, str, str, str] | None:
    action = _optional_string(item.get("action"))
    match = _optional_string(item.get("match")) or "literal"
    pattern = _optional_string(item.get("pattern"))
    document_type = _optional_string(item.get("document_type"))
    if not document_type:
        context = item.get("artifact_context")
        if isinstance(context, dict):
            document_type = _optional_string(context.get("document_type"))
    if not action or not match or not pattern or not document_type or document_type == "unknown":
        return None
    return (document_type, action, match, pattern)

def _dedupe_feedback_items(items: list[dict]) -> list[dict]:
    seen = set()
    result = []
    for item in items:
        key = _feedback_cluster_key(item)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result

def _dictionary_suggestion_for_document_type(
    document_type: str,
    items: list[dict],
    rejected_keys: set[tuple[str, str, str, str]],
) -> dict:
    proposed_rules = []
    for item in items:
        key = _feedback_cluster_key(item)
        if not key or key in rejected_keys:
            continue
        proposed_rules.append({
            "action": item.get("action"),
            "match": item.get("match", "literal"),
            "pattern": item.get("pattern"),
            "reason": item.get("reason", "learned from accepted feedback"),
            "examples": _proposal_string_list(item.get("examples")),
            "source_proposal_id": item.get("id"),
            "accepted_rule_id": item.get("accepted_rule_id"),
            "created_from_run": item.get("created_from_run"),
            "artifact_context": item.get("artifact_context") if isinstance(item.get("artifact_context"), dict) else {},
        })

    return {
        "schema": "kbprep.dictionary_suggestion.v1",
        "document_type": document_type,
        "target": f"rules/document_types/{document_type}.json",
        "required_confirmation": True,
        "feedback_count": len(proposed_rules),
        "proposed_rules": proposed_rules,
        "blocked_by_rejected_feedback": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "review_note": "Copy into a document-type dictionary only after checking examples, counterexamples, and current source outputs.",
    }
