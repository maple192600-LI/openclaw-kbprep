"""Pattern matching and small feedback value helpers."""

import re

from ..envelope import fail

def _matching_snippets(text: str, pattern: str, match: str, limit: int = 8) -> list[str]:
    snippets = []
    for line in text.splitlines():
        cleaned = _clean_snippet_line(line)
        if not cleaned:
            continue
        if _matches_pattern(cleaned, pattern, match):
            snippets.append(cleaned[:240])
            if len(snippets) >= limit:
                break
    return snippets

def _matches_pattern(text: str, pattern: str, match: str) -> bool:
    if match == "regex":
        try:
            return re.search(pattern, text, re.IGNORECASE) is not None
        except re.error:
            return False
    return pattern.lower() in text.lower()

def _clean_snippet_line(line: str) -> str:
    line = re.sub(r"^\s{0,3}#{1,6}\s*", "", line)
    line = re.sub(r"^\s*[-*+]\s+", "", line)
    line = re.sub(r"\s+", " ", line).strip()
    return line

def _looks_like_body_counterexample(line: str, pattern: str) -> bool:
    if line.strip() == pattern.strip():
        return False
    return bool(re.search(r"(案例|示例|样本|字段|步骤|参数|代码|保留|正文|上下文)", line))

def _dedupe_strings(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        cleaned = value.strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result

def _optional_string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None

def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        fail("E_INVALID_INPUT", "examples and counterexamples must be lists")
        raise AssertionError("unreachable")
    result = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            fail("E_INVALID_INPUT", "examples and counterexamples must contain non-empty strings")
        result.append(item.strip())
    return result
