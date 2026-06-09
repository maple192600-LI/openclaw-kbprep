"""Frontmatter formatting helpers for Obsidian knowledge-base output."""

from __future__ import annotations


def _yaml_safe(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def frontmatter_lines(fields: dict[str, str]) -> list[str]:
    lines = ["---"]
    for key, value in fields.items():
        lines.append(f'{key}: "{_yaml_safe(value)}"')
    lines.append("---")
    return lines
