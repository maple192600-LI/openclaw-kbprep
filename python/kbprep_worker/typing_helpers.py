"""Small helpers for narrowing JSON-shaped values before business logic."""

from __future__ import annotations

import os
from typing import Any, TypeAlias

from .envelope import fail

JsonValue: TypeAlias = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]
JsonList: TypeAlias = list[JsonValue]


def as_object(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def as_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def as_int(value: object, *, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def as_path_string(value: object) -> str | None:
    if isinstance(value, os.PathLike):
        text = os.fspath(value)
    elif isinstance(value, str):
        text = value
    else:
        return None
    text = text.strip()
    return text or None


def require_object(value: object, *, field_name: str, code: str = "E_INVALID_INPUT") -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    fail(
        code,
        f"{field_name} must be a JSON object.",
        details={"field": field_name, "actual_type": type(value).__name__},
        recoverable=True,
        suggested_action="Regenerate the affected JSON artifact and retry.",
    )
    raise AssertionError("unreachable")
