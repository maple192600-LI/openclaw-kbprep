"""Input parsing for the feedback command."""

import re
from pathlib import Path

from ..envelope import fail
from ..rule_loader import load_cleaning_rules, rules_root
from ..typing_helpers import as_int
from .patterns import _optional_string, _string_list

def _target_rules_dir(data: dict) -> Path:
    value = _optional_string(data.get("target_rules_dir"))
    if value:
        return Path(value).expanduser().resolve()
    return rules_root()

def _positive_int(value: object, default: int) -> int:
    parsed = as_int(value, default=default) if value is not None else default
    return max(1, parsed)

def _required_path(data: dict, key: str) -> Path:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        fail("E_INPUT_NOT_FOUND", f"{key} is required")
        raise AssertionError("unreachable")
    path = Path(value).expanduser().resolve()
    if key == "run_dir" and not path.exists():
        fail("E_INPUT_NOT_FOUND", f"run_dir does not exist: {path}")
    return path

def _feedback_text(data: dict) -> str:
    inline = _optional_string(data.get("feedback_text"))
    if inline:
        return inline
    feedback_file = _optional_string(data.get("feedback_file"))
    if feedback_file:
        path = Path(feedback_file).expanduser().resolve()
        if not path.exists():
            fail("E_INPUT_NOT_FOUND", f"feedback_file does not exist: {path}")
        text = path.read_text(encoding="utf-8").strip()
        if text:
            return text
    fail("E_INPUT_NOT_FOUND", "feedback_text or feedback_file is required")
    return ""

def _rules_dir(data: dict) -> Path:
    value = _optional_string(data.get("rules_dir"))
    if value:
        return Path(value).expanduser().resolve()
    return Path.cwd() / ".kbprep" / "rules" / "user"

def _action(data: dict, text: str) -> str:
    explicit = _optional_string(data.get("action"))
    if explicit:
        if explicit not in {"discard", "review", "protect"}:
            fail("E_INVALID_INPUT", "action must be discard, review, or protect")
        return explicit
    rules = load_cleaning_rules()
    if _matches_feedback_intent(text, rules.feedback_protect_intent_terms):
        return "protect"
    if _matches_feedback_intent(text, rules.feedback_discard_intent_terms):
        return "discard"
    return "review"

def _matches_feedback_intent(text: str, terms: tuple[str, ...]) -> bool:
    text_norm = text.casefold()
    return any(term.casefold() in text_norm for term in terms if term)

def _scope(data: dict) -> str:
    scope = _optional_string(data.get("scope")) or "user"
    if scope not in {"global", "user", "project", "document_type", "source_pattern"}:
        fail("E_INVALID_INPUT", "scope must be global, user, project, document_type, or source_pattern")
    return scope

def _match_type(data: dict) -> str:
    match = _optional_string(data.get("match")) or "literal"
    if match not in {"literal", "regex"}:
        fail("E_INVALID_INPUT", "match must be literal or regex")
    return match

def _pattern(data: dict, feedback_text: str) -> str:
    explicit = _optional_string(data.get("pattern"))
    if explicit:
        return explicit
    quoted = re.findall(r"[「“\"']([^」”\"']{2,120})[」”\"']", feedback_text)
    if quoted:
        return quoted[0].strip()
    examples = _string_list(data.get("examples"))
    if examples:
        return examples[0].strip()[:120]
    cleaned = re.sub(r"\s+", " ", feedback_text).strip()
    return cleaned[:120] if cleaned else "manual feedback"
