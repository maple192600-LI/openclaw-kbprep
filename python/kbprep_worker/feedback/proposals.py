"""Feedback rule proposal creation, acceptance, rejection, and narrowing."""

import re
from datetime import datetime, timezone
from uuid import uuid4

from ..envelope import fail, ok
from ..rule_schema import validate_rule_proposal
from .inputs import _rules_dir
from .jsonl_store import _append_jsonl_locked, _read_jsonl
from .patterns import (
    _dedupe_strings,
    _looks_like_body_counterexample,
    _matches_pattern,
    _matching_snippets,
    _optional_string,
    _string_list,
)
from .rerun_verification import _rerun_after_accept

def _accept_proposal(data: dict) -> None:
    rules_dir = _rules_dir(data)
    proposed_path = rules_dir / "proposed_rules.jsonl"
    accepted_path = rules_dir / "accepted_rules.jsonl"
    rejected_path = rules_dir / "rejected_rules.jsonl"
    wanted = _optional_string(data.get("accept_proposal"))
    if not wanted:
        fail("E_INPUT_NOT_FOUND", "accept_proposal is required")
    if not proposed_path.exists():
        fail("E_INPUT_NOT_FOUND", f"proposed_rules.jsonl does not exist: {proposed_path}")

    proposals = _read_jsonl(proposed_path)
    selected = proposals[-1] if wanted == "latest" and proposals else next(
        (proposal for proposal in proposals if proposal.get("id") == wanted),
        None,
    )
    if not selected:
        fail("E_INPUT_NOT_FOUND", f"proposal not found: {wanted}")
        raise AssertionError("unreachable")
    validate_rule_proposal(selected, str(proposed_path))
    rejected_existing = _read_jsonl(rejected_path) if rejected_path.exists() else []
    if any(item.get("id") == selected.get("id") for item in rejected_existing):
        fail("E_INVALID_INPUT", f"proposal has been rejected and cannot be accepted: {wanted}")

    accepted_existing = _read_jsonl(accepted_path) if accepted_path.exists() else []
    if any(item.get("id") == selected.get("id") for item in accepted_existing):
        ok(data={
            "accepted": selected,
            "accepted_path": str(accepted_path),
            "already_accepted": True,
        })

    validation = _validate_proposal_acceptance(selected)
    if not validation["ok"]:
        suggested = _suggest_narrowed_proposal(selected, validation)
        if suggested:
            _append_jsonl_locked(proposed_path, suggested)
            validation = {**validation, "suggested_proposal": suggested}
        fail(
            "E_RULE_VALIDATION_FAILED",
            "Feedback rule proposal failed acceptance validation.",
            details=validation,
            recoverable=True,
            suggested_action="Review the suggested narrower proposal, then accept or reject it explicitly.",
        )

    accepted = {
        **selected,
        "status": "accepted",
        "accepted_at": datetime.now(timezone.utc).isoformat(),
        "accepted_rule_id": f"user-feedback-{selected['id']}",
        "acceptance_validation": validation,
        "requires_confirmation": True,
    }
    validate_rule_proposal(accepted, "accepted feedback")
    rules_dir.mkdir(parents=True, exist_ok=True)
    _append_jsonl_locked(accepted_path, accepted)

    rerun_verification = _rerun_after_accept(accepted, rules_dir, data)

    ok(data={
        "accepted": accepted,
        "accepted_path": str(accepted_path),
        "rerun_verification": rerun_verification,
        "next_step": "Rerun the affected source and inspect quality_report.json, discarded.md, and review_needed.md.",
    })

def _reject_proposal(data: dict) -> None:
    rules_dir = _rules_dir(data)
    proposed_path = rules_dir / "proposed_rules.jsonl"
    rejected_path = rules_dir / "rejected_rules.jsonl"
    accepted_path = rules_dir / "accepted_rules.jsonl"
    wanted = _optional_string(data.get("reject_proposal"))
    if not wanted:
        fail("E_INPUT_NOT_FOUND", "reject_proposal is required")
    if not proposed_path.exists():
        fail("E_INPUT_NOT_FOUND", f"proposed_rules.jsonl does not exist: {proposed_path}")

    proposals = _read_jsonl(proposed_path)
    selected = proposals[-1] if wanted == "latest" and proposals else next(
        (proposal for proposal in proposals if proposal.get("id") == wanted),
        None,
    )
    if not selected:
        fail("E_INPUT_NOT_FOUND", f"proposal not found: {wanted}")
        raise AssertionError("unreachable")
    validate_rule_proposal(selected, str(proposed_path))

    accepted_existing = _read_jsonl(accepted_path) if accepted_path.exists() else []
    if any(item.get("id") == selected.get("id") for item in accepted_existing):
        fail("E_INVALID_INPUT", f"proposal has already been accepted and cannot be rejected: {wanted}")

    rejected_existing = _read_jsonl(rejected_path) if rejected_path.exists() else []
    if any(item.get("id") == selected.get("id") for item in rejected_existing):
        ok(data={
            "rejected": selected,
            "rejected_path": str(rejected_path),
            "already_rejected": True,
        })

    rejected = {
        **selected,
        "status": "rejected",
        "rejected_at": datetime.now(timezone.utc).isoformat(),
        "reject_reason": _optional_string(data.get("reject_reason")) or "Rejected by user or reviewing agent.",
        "requires_confirmation": True,
    }
    validate_rule_proposal(rejected, "rejected feedback")
    rules_dir.mkdir(parents=True, exist_ok=True)
    _append_jsonl_locked(rejected_path, rejected)

    ok(data={
        "rejected": rejected,
        "rejected_path": str(rejected_path),
        "next_step": "Do not promote this proposal. Keep it as feedback memory so future agents do not suggest it again.",
    })

def _examples(
    data: dict,
    feedback_text: str,
    pattern: str,
    match: str,
    action: str,
    artifacts: dict,
) -> list[str]:
    examples = _string_list(data.get("examples"))
    if examples:
        return examples
    sources: tuple[str, ...]
    if action == "discard":
        sources = ("discarded", "review_needed")
    elif action == "protect":
        sources = ("discarded", "cleaned", "review_needed")
    else:
        sources = ("review_needed", "discarded", "cleaned")
    result: list[str] = []
    for source in sources:
        result.extend(_matching_snippets(artifacts["texts"].get(source, ""), pattern, match))
    result.append(pattern)
    return _dedupe_strings(result)[:8]

def _counterexamples(data: dict, pattern: str, match: str, action: str, artifacts: dict) -> list[str]:
    explicit = _string_list(data.get("counterexamples"))
    if explicit:
        return explicit
    if action != "discard":
        return []
    result = []
    for line in _matching_snippets(artifacts["texts"].get("cleaned", ""), pattern, match, limit=12):
        if _looks_like_body_counterexample(line, pattern):
            result.append(line)
    return _dedupe_strings(result)[:5]

def _validate_proposal_acceptance(proposal: dict) -> dict:
    pattern = str(proposal.get("pattern", ""))
    match = str(proposal.get("match", "literal"))
    examples = _proposal_string_list(proposal.get("examples"))
    counterexamples = _proposal_string_list(proposal.get("counterexamples"))
    example_misses = [
        value for value in examples
        if not _matches_pattern(value, pattern, match)
    ]
    counterexample_matches = [
        value for value in counterexamples
        if _matches_pattern(value, pattern, match)
    ]
    return {
        "ok": not example_misses and not counterexample_matches,
        "example_count": len(examples),
        "counterexample_count": len(counterexamples),
        "example_misses": example_misses[:10],
        "counterexample_matches": counterexample_matches[:10],
    }

def _proposal_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if isinstance(item, str) and item.strip():
            result.append(item.strip())
    return result

def _suggest_narrowed_proposal(proposal: dict, validation: dict) -> dict | None:
    if proposal.get("action") != "discard":
        return None
    if not validation.get("counterexample_matches"):
        return None

    match = str(proposal.get("match", "literal"))
    if match != "literal":
        return None

    current_pattern = str(proposal.get("pattern", "")).strip()
    examples = _proposal_string_list(proposal.get("examples"))
    counterexamples = _proposal_string_list(proposal.get("counterexamples"))
    candidates = [
        example for example in examples
        if example.strip()
        and example.strip() != current_pattern
        and current_pattern.lower() in example.lower()
    ]
    candidates.sort(key=lambda value: (len(value), value))

    regex_narrowed = _regex_narrowed_from_examples(proposal, candidates, counterexamples, current_pattern)
    if regex_narrowed:
        return regex_narrowed

    narrowed_pattern = next(
        (
            candidate for candidate in candidates
            if not any(candidate.lower() in counterexample.lower() for counterexample in counterexamples)
        ),
        None,
    )
    if not narrowed_pattern:
        return None

    narrowed = {
        **proposal,
        "id": f"proposal-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}",
        "status": "proposed",
        "pattern": narrowed_pattern[:120],
        "match": "literal",
        "examples": _dedupe_strings([narrowed_pattern, *candidates])[:8],
        "counterexamples": [
            value for value in counterexamples
            if narrowed_pattern.lower() in value.lower()
        ][:5],
        "parent_proposal_id": proposal.get("id"),
        "narrowed_from_pattern": current_pattern,
        "narrowing_reason": "Original proposal matched counterexamples; narrowed to a concrete run-artifact example.",
        "requires_confirmation": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    narrowed.update(_narrowed_scope_from_artifacts(proposal))
    validate_rule_proposal(narrowed, "narrowed feedback proposal")
    if not _validate_proposal_acceptance(narrowed)["ok"]:
        return None
    return narrowed

def _regex_narrowed_from_examples(
    proposal: dict,
    candidates: list[str],
    counterexamples: list[str],
    current_pattern: str,
) -> dict | None:
    if len(candidates) < 2:
        return None
    regex = _number_variant_regex(candidates)
    if not regex:
        return None
    if not all(_matches_pattern(candidate, regex, "regex") for candidate in candidates):
        return None
    regex_counterexamples = [
        value for value in counterexamples
        if _matches_pattern(value, regex, "regex")
    ]
    if regex_counterexamples:
        return None

    narrowed = {
        **proposal,
        "id": f"proposal-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}",
        "status": "proposed",
        "pattern": regex,
        "match": "regex",
        "examples": _dedupe_strings(candidates)[:8],
        "counterexamples": [],
        "parent_proposal_id": proposal.get("id"),
        "narrowed_from_pattern": current_pattern,
        "narrowing_reason": "Original proposal matched counterexamples; multiple run-artifact examples support a narrower regex.",
        "requires_confirmation": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    narrowed.update(_narrowed_scope_from_artifacts(proposal))
    validate_rule_proposal(narrowed, "narrowed feedback regex proposal")
    if not _validate_proposal_acceptance(narrowed)["ok"]:
        return None
    return narrowed

def _number_variant_regex(values: list[str]) -> str | None:
    tokenized = [re.split(r"(\d+)", value.strip()) for value in values if value.strip()]
    if len(tokenized) < 2:
        return None
    first = tokenized[0]
    if not any(part.isdigit() for part in first):
        return None
    for tokens in tokenized[1:]:
        if len(tokens) != len(first):
            return None
        for left, right in zip(first, tokens):
            if left.isdigit() and right.isdigit():
                continue
            if left != right:
                return None
    return "".join(r"\d+" if part.isdigit() else re.escape(part) for part in first)

def _narrowed_scope_from_artifacts(proposal: dict) -> dict:
    if proposal.get("scope") in {"document_type", "source_pattern"}:
        return {}
    artifact_context = proposal.get("artifact_context")
    if not isinstance(artifact_context, dict):
        return {}
    document_type = _optional_string(artifact_context.get("document_type"))
    if document_type and document_type != "unknown":
        return {
            "scope": "document_type",
            "document_type": document_type,
            "narrowed_scope_reason": "Run artifact context identified a document type, so the follow-up proposal is limited to that document type.",
        }
    source_name = _optional_string(artifact_context.get("source_name"))
    if source_name:
        return {
            "scope": "source_pattern",
            "source_pattern": source_name,
            "narrowed_scope_reason": "Run artifact context identified a source file, so the follow-up proposal is limited to that source pattern.",
        }
    return {}

def _reason(data: dict, feedback_text: str) -> str:
    explicit = _optional_string(data.get("reason"))
    if explicit:
        return explicit
    return feedback_text[:500]

def _confidence(data: dict) -> str | float:
    value = data.get("confidence")
    if isinstance(value, (int, float)):
        return float(value)
    text = _optional_string(value)
    return text or "needs_review"
