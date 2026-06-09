"""
Load KBPrep cleaning dictionaries from the repository-level rules directory.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .rule_schema import ClassificationPattern, CleaningRule, validate_rule_file, validate_rule_proposal


@dataclass(frozen=True)
class LoadedCleaningRules:
    promotional_line_rules: tuple[CleaningRule, ...]
    cta_keywords: tuple[str, ...]
    qr_image_markers: tuple[str, ...]
    image_qr_indicators: tuple[str, ...]
    image_marketing_indicators: tuple[str, ...]
    image_operation_indicators: tuple[str, ...]
    image_proof_indicators: tuple[str, ...]
    image_educational_heading_indicators: tuple[str, ...]
    tutorial_indicators: tuple[str, ...]
    knowledge_terms: tuple[str, ...]
    refund_patterns: tuple[str, ...]
    footer_patterns: tuple[str, ...]
    evidence_patterns: tuple[ClassificationPattern, ...]
    marketing_wrapper_heading_terms: tuple[str, ...]
    marketing_wrapper_back_matter_terms: tuple[str, ...]
    marketing_wrapper_line_patterns: tuple[str, ...]
    business_method_context_terms: tuple[str, ...]
    transcript_filler_patterns: tuple[str, ...]
    protected_patterns: tuple[ClassificationPattern, ...]
    feedback_protect_intent_terms: tuple[str, ...]
    feedback_discard_intent_terms: tuple[str, ...]
    sources: tuple[str, ...]


def rules_root() -> Path:
    override = os.environ.get("KBPREP_RULES_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return builtin_rules_root()


def builtin_rules_root() -> Path:
    return Path(__file__).resolve().parents[2] / "rules"


def profile_templates(profile: str = "standard") -> tuple[str, ...]:
    if profile == "curated_obsidian_kb":
        return ("self_media_course",)
    return ()


@lru_cache(maxsize=64)
def load_cleaning_rules(
    profile: str = "standard",
    document_type: str = "",
    templates: tuple[str, ...] = (),
    source_identity: str = "",
) -> LoadedCleaningRules:
    selected = [
        rules_root() / "base" / "obvious_noise.json",
    ]
    if document_type:
        selected.append(rules_root() / "document_types" / f"{document_type}.json")
    for template in (*profile_templates(profile), *templates):
        selected.append(rules_root() / "templates" / f"{template}.json")

    promotional_line_rules: list[CleaningRule] = []
    cta_keywords: list[str] = []
    qr_image_markers: list[str] = []
    image_qr_indicators: list[str] = []
    image_marketing_indicators: list[str] = []
    image_operation_indicators: list[str] = []
    image_proof_indicators: list[str] = []
    image_educational_heading_indicators: list[str] = []
    tutorial_indicators: list[str] = []
    knowledge_terms: list[str] = []
    refund_patterns: list[str] = []
    footer_patterns: list[str] = []
    evidence_patterns: list[ClassificationPattern] = []
    marketing_wrapper_heading_terms: list[str] = []
    marketing_wrapper_back_matter_terms: list[str] = []
    marketing_wrapper_line_patterns: list[str] = []
    business_method_context_terms: list[str] = []
    transcript_filler_patterns: list[str] = []
    protected_patterns: list[ClassificationPattern] = []
    feedback_protect_intent_terms: list[str] = []
    feedback_discard_intent_terms: list[str] = []
    sources: list[str] = []

    for path in selected:
        if not path.exists():
            continue
        source = str(path.relative_to(rules_root().parent))
        with path.open("r", encoding="utf-8") as fh:
            rule_set = validate_rule_file(json.load(fh), source)
        promotional_line_rules.extend(rule_set.promotional_line_rules)
        cta_keywords.extend(rule_set.cta_keywords)
        qr_image_markers.extend(rule_set.qr_image_markers)
        image_qr_indicators.extend(rule_set.image_qr_indicators)
        image_marketing_indicators.extend(rule_set.image_marketing_indicators)
        image_operation_indicators.extend(rule_set.image_operation_indicators)
        image_proof_indicators.extend(rule_set.image_proof_indicators)
        image_educational_heading_indicators.extend(rule_set.image_educational_heading_indicators)
        tutorial_indicators.extend(rule_set.tutorial_indicators)
        knowledge_terms.extend(rule_set.knowledge_terms)
        refund_patterns.extend(rule_set.refund_patterns)
        footer_patterns.extend(rule_set.footer_patterns)
        evidence_patterns.extend(rule_set.evidence_patterns)
        marketing_wrapper_heading_terms.extend(rule_set.marketing_wrapper_heading_terms)
        marketing_wrapper_back_matter_terms.extend(rule_set.marketing_wrapper_back_matter_terms)
        marketing_wrapper_line_patterns.extend(rule_set.marketing_wrapper_line_patterns)
        business_method_context_terms.extend(rule_set.business_method_context_terms)
        transcript_filler_patterns.extend(rule_set.transcript_filler_patterns)
        protected_patterns.extend(rule_set.protected_patterns)
        feedback_protect_intent_terms.extend(rule_set.feedback_protect_intent_terms)
        feedback_discard_intent_terms.extend(rule_set.feedback_discard_intent_terms)
        sources.append(rule_set.source)

    for path in _accepted_rule_paths():
        if not path.exists():
            continue
        accepted_rules = _load_accepted_rule_proposals(path, document_type, source_identity)
        promotional_line_rules.extend(accepted_rules)
        if accepted_rules:
            sources.append(_source_name(path))

    return LoadedCleaningRules(
        promotional_line_rules=tuple(promotional_line_rules),
        cta_keywords=tuple(_dedupe(cta_keywords)),
        qr_image_markers=tuple(_dedupe(qr_image_markers)),
        image_qr_indicators=tuple(_dedupe(image_qr_indicators)),
        image_marketing_indicators=tuple(_dedupe(image_marketing_indicators)),
        image_operation_indicators=tuple(_dedupe(image_operation_indicators)),
        image_proof_indicators=tuple(_dedupe(image_proof_indicators)),
        image_educational_heading_indicators=tuple(_dedupe(image_educational_heading_indicators)),
        tutorial_indicators=tuple(_dedupe(tutorial_indicators)),
        knowledge_terms=tuple(_dedupe(knowledge_terms)),
        refund_patterns=tuple(_dedupe(refund_patterns)),
        footer_patterns=tuple(_dedupe(footer_patterns)),
        evidence_patterns=tuple(_dedupe_classification_patterns(evidence_patterns)),
        marketing_wrapper_heading_terms=tuple(_dedupe(marketing_wrapper_heading_terms)),
        marketing_wrapper_back_matter_terms=tuple(_dedupe(marketing_wrapper_back_matter_terms)),
        marketing_wrapper_line_patterns=tuple(_dedupe(marketing_wrapper_line_patterns)),
        business_method_context_terms=tuple(_dedupe(business_method_context_terms)),
        transcript_filler_patterns=tuple(_dedupe(transcript_filler_patterns)),
        protected_patterns=tuple(_dedupe_classification_patterns(protected_patterns)),
        feedback_protect_intent_terms=tuple(_dedupe(feedback_protect_intent_terms)),
        feedback_discard_intent_terms=tuple(_dedupe(feedback_discard_intent_terms)),
        sources=tuple(sources),
    )


def rule_matches(rule: CleaningRule, text: str) -> bool:
    if rule.match == "literal":
        return rule.pattern.lower() in text.lower()
    return re.search(rule.pattern, text, re.IGNORECASE) is not None


def _accepted_rule_paths() -> list[Path]:
    paths = [
        rules_root() / "user" / "accepted_rules.jsonl",
        Path.cwd() / ".kbprep" / "rules" / "user" / "accepted_rules.jsonl",
    ]
    env_value = os.environ.get("KBPREP_USER_RULES_DIR", "").strip()
    if env_value:
        for raw in env_value.split(os.pathsep):
            if raw.strip():
                paths.append(Path(raw).expanduser().resolve() / "accepted_rules.jsonl")
    return _dedupe_paths(paths)


def _load_accepted_rule_proposals(path: Path, document_type: str, source_identity: str) -> list[CleaningRule]:
    result: list[CleaningRule] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                raw = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON: {exc.msg}") from exc
            proposal = validate_rule_proposal(raw, f"{path}:{line_no}")
            if raw.get("status") != "accepted":
                continue
            proposal_document_type = raw.get("document_type")
            if raw.get("scope") == "document_type" and proposal_document_type and proposal_document_type != document_type:
                continue
            if raw.get("scope") == "source_pattern":
                if not _source_pattern_matches(raw, source_identity):
                    continue
            result.append(CleaningRule(
                rule_id=str(raw.get("accepted_rule_id") or proposal.proposal_id),
                action=proposal.action,
                match=proposal.match,
                pattern=proposal.pattern,
                reason=proposal.reason,
                risk_tag=f"user_feedback_{proposal.action}",
                source=_source_name(path),
            ))
    return result


def _source_pattern_matches(raw: dict, source_identity: str) -> bool:
    pattern = str(raw.get("source_pattern") or "").strip()
    if not pattern:
        return False
    candidates = _source_identity_candidates(source_identity)
    if not candidates:
        return False
    pattern_norm = pattern.replace("\\", "/").lower()
    field, _, field_pattern = pattern_norm.partition(":")
    if field_pattern and field in {"input_path", "source_path", "source_name", "source_url", "source_domain", "site_name", "origin", "origin_url"}:
        return any(
            candidate_key == field and _keyed_source_pattern_matches(field, field_pattern, candidate_value)
            for candidate_key, candidate_value in candidates
        )
    return any(_plain_source_pattern_matches(pattern_norm, candidate_key, candidate_value) for candidate_key, candidate_value in candidates)


def _keyed_source_pattern_matches(field: str, pattern: str, value: str) -> bool:
    if field == "source_domain":
        return value == pattern or value.endswith(f".{pattern}")
    if field in {"source_url", "origin_url"}:
        return _url_prefix_boundary_matches(pattern, value)
    if field in {"input_path", "source_path", "source_name"}:
        return _path_or_name_prefix_matches(pattern, value)
    return _text_prefix_boundary_matches(pattern, value)


def _plain_source_pattern_matches(pattern: str, field: str, value: str) -> bool:
    if field == "source_domain":
        return value == pattern or value.endswith(f".{pattern}")
    if field in {"source_url", "origin_url"}:
        return _url_prefix_boundary_matches(pattern, value)
    if field in {"input_path", "source_path", "source_name", "source_identity"}:
        return _path_or_name_prefix_matches(pattern, value)
    return _text_prefix_boundary_matches(pattern, value)


def _url_prefix_boundary_matches(pattern: str, value: str) -> bool:
    if value == pattern:
        return True
    if not value.startswith(pattern):
        return False
    remainder = value[len(pattern):]
    return not remainder or remainder[0] in {"/", "?", "#", "&"}


def _path_or_name_prefix_matches(pattern: str, value: str) -> bool:
    parts = [part for part in re.split(r"[\\/]+", value) if part]
    return any(_text_prefix_boundary_matches(pattern, part) for part in parts)


def _text_prefix_boundary_matches(pattern: str, value: str) -> bool:
    if value == pattern:
        return True
    if not value.startswith(pattern):
        return False
    remainder = value[len(pattern):]
    return bool(remainder) and remainder[0] in {"-", "_", ".", " ", "~", "(", "[", "{"}


def _source_identity_candidates(source_identity: str) -> list[tuple[str, str]]:
    raw = str(source_identity or "").strip()
    if not raw:
        return []
    result: list[tuple[str, str]] = []
    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = None
    if isinstance(parsed, dict):
        _collect_source_identity(parsed, result)
    else:
        result.append(("source_identity", raw))
    return _dedupe_identity_candidates(result)


def _collect_source_identity(value: dict, result: list[tuple[str, str]], prefix: str = "") -> None:
    for key, raw_value in value.items():
        key_text = str(key).strip()
        full_key = f"{prefix}.{key_text}" if prefix else key_text
        normalized_key = key_text.lower()
        if isinstance(raw_value, dict):
            _collect_source_identity(raw_value, result, full_key)
            continue
        if isinstance(raw_value, list):
            for item in raw_value:
                if isinstance(item, (str, int, float)):
                    result.append((normalized_key, str(item)))
            continue
        if isinstance(raw_value, (str, int, float)):
            result.append((normalized_key, str(raw_value)))
            if full_key != key_text:
                result.append((full_key.lower(), str(raw_value)))


def _dedupe_identity_candidates(values: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen = set()
    result = []
    for key, value in values:
        normalized = value.replace("\\", "/").lower().strip()
        if not normalized:
            continue
        item = (key.lower(), normalized)
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _source_name(path: Path) -> str:
    try:
        return str(path.relative_to(rules_root().parent))
    except ValueError:
        return str(path)


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen = set()
    result = []
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def _dedupe_classification_patterns(values: list[ClassificationPattern]) -> list[ClassificationPattern]:
    seen = set()
    result = []
    for value in values:
        key = (value.label.lower(), value.pattern.lower())
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result
