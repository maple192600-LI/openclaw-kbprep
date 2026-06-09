"""Infer feedback proposal scope from source identity and repeated feedback."""

import json
import re
from pathlib import Path
from urllib.parse import urlparse

from ..envelope import fail
from .inputs import _scope
from .jsonl_store import _read_jsonl
from .patterns import _dedupe_strings, _optional_string

def _source_pattern_payload(data: dict, artifacts: dict) -> dict:
    if _scope(data) != "source_pattern":
        return {}
    explicit = _optional_string(data.get("source_pattern"))
    if explicit:
        return {"source_pattern": explicit}
    inferred_identity = _best_source_identity_pattern([artifacts["context"]])
    if inferred_identity:
        return {"source_pattern": inferred_identity}
    inferred = _optional_string(artifacts["context"].get("source_name"))
    if inferred:
        return {"source_pattern": inferred}
    fail("E_INVALID_INPUT", "source_pattern is required when scope is source_pattern and it cannot be inferred from run metadata")
    return {}

def _proposal_scope_payload(
    data: dict,
    artifacts: dict,
    rules_dir: Path,
    action: str,
    match: str,
    pattern: str,
) -> dict:
    if _optional_string(data.get("scope")):
        return {"scope": _scope(data), **_source_pattern_payload(data, artifacts)}

    repeat = _repeat_feedback_source_pattern(rules_dir, artifacts, action, match, pattern)
    if repeat:
        return {
            "scope": "source_pattern",
            "source_pattern": repeat["source_pattern"],
            "repeat_feedback": repeat,
        }
    return {"scope": _scope(data)}

def _repeat_feedback_source_pattern(
    rules_dir: Path,
    artifacts: dict,
    action: str,
    match: str,
    pattern: str,
) -> dict | None:
    current_context = artifacts.get("context") if isinstance(artifacts.get("context"), dict) else {}
    current_source = _optional_string(current_context.get("source_name"))
    current_identity = _source_identity_from_context(current_context)
    if not current_source and not current_identity:
        return None

    related = []
    for name in ("proposed_rules.jsonl", "accepted_rules.jsonl"):
        path = rules_dir / name
        for item in _read_jsonl(path) if path.exists() else []:
            if item.get("action") != action:
                continue
            if item.get("match", "literal") != match:
                continue
            if str(item.get("pattern", "")) != pattern:
                continue
            context = item.get("artifact_context")
            if not isinstance(context, dict):
                continue
            source_name = _optional_string(context.get("source_name"))
            source_identity = _source_identity_from_context(context)
            if not source_name and not source_identity:
                continue
            if source_name == current_source and source_identity == current_identity:
                continue
            related.append(item)

    if not related:
        return None

    contexts = [
        *[
            item.get("artifact_context")
            for item in related
            if isinstance(item.get("artifact_context"), dict)
        ],
        current_context,
    ]
    source_names = _dedupe_strings([
        *[
            str(item.get("artifact_context", {}).get("source_name"))
            for item in related
            if isinstance(item.get("artifact_context"), dict)
        ],
        current_source,
    ])
    source_identity_patterns = _source_identity_patterns_from_contexts(contexts)
    source_pattern = source_identity_patterns[0] if source_identity_patterns else _source_pattern_from_repeated_names(source_names)
    if not source_pattern:
        return None

    return {
        "matching_feedback_count": len(related),
        "source_names": sorted(source_names),
        "source_identity_patterns": source_identity_patterns,
        "source_pattern": source_pattern,
        "related_proposal_ids": [
            str(item.get("id"))
            for item in related
            if item.get("id")
        ],
        "narrowing_reason": "repeated feedback for the same pattern appeared in related source files, so the proposal is limited to a source_pattern.",
    }

def _source_pattern_from_repeated_names(source_names: list[str]) -> str | None:
    if len(source_names) < 2:
        return None
    stems = [Path(name).stem for name in source_names if name.strip()]
    if len(stems) < 2:
        return None
    prefix = stems[0]
    for stem in stems[1:]:
        while prefix and not stem.startswith(prefix):
            prefix = prefix[:-1]
    prefix = re.sub(r"[\d\W_]+$", "", prefix, flags=re.UNICODE)
    if len(prefix) >= 3:
        return prefix
    return None

def _source_identity_patterns_from_contexts(contexts: list[dict]) -> list[str]:
    if len(contexts) < 2:
        return []
    candidates: list[str] = []
    domains = _dedupe_strings([
        domain
        for context in contexts
        for domain in [_source_domain_from_context(context)]
        if domain
    ])
    if len(domains) == 1:
        candidates.append(f"source_domain:{domains[0]}")

    for key in ("site_name", "origin", "source_title"):
        values = _dedupe_strings([
            value
            for context in contexts
            for value in [_source_identity_value(context, key)]
            if value
        ])
        if len(values) == 1:
            candidates.append(f"{key}:{values[0]}")

    urls = _dedupe_strings([
        value
        for context in contexts
        for value in [
            _source_identity_value(context, "source_url"),
            _source_identity_value(context, "origin_url"),
        ]
        if value
    ])
    if len(urls) == 1:
        candidates.append(f"source_url:{urls[0]}")

    return candidates

def _best_source_identity_pattern(contexts: list[dict]) -> str | None:
    patterns = _source_identity_patterns_from_contexts(contexts)
    return patterns[0] if patterns else None

def _source_domain_from_context(context: dict) -> str:
    explicit = _source_identity_value(context, "source_domain")
    if explicit:
        return explicit.lower().removeprefix("www.")
    for key in ("source_url", "origin_url"):
        value = _source_identity_value(context, key)
        if not value:
            continue
        parsed = urlparse(value)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        if domain:
            return domain
    return ""

def _source_identity_value(context: dict, key: str) -> str:
    identity = _source_identity_from_context(context)
    value = identity.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    nested = identity.get("source_metadata")
    if isinstance(nested, dict):
        nested_value = nested.get(key)
        if isinstance(nested_value, str) and nested_value.strip():
            return nested_value.strip()
    value = context.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return ""

def _source_identity_from_context(context: dict) -> dict:
    value = context.get("source_identity")
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except Exception:
            return {"source_identity": value.strip()}
        if isinstance(parsed, dict):
            return parsed
        return {"source_identity": value.strip()}
    return {}
