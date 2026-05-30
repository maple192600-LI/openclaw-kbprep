"""
patch_guard — apply RFC 6902 JSON Patch with safety guardrails.
Supports: replace, add, remove on /lines/N paths.
"""
import json
import logging
import re
from pathlib import Path

from .envelope import ok, fail

logger = logging.getLogger(__name__)

# Protected patterns that must not be deleted or rewritten
PROTECTED_PATTERNS = [
    (re.compile(r"^\s*(?:\d+[\.\)、)]\s+|第?[一二三四五六七八九十百千\d]+步[骤]?[：:、\.\s]|步骤\s*[一二三四五六七八九十百千\d]+[：:、\.\s])"), "step_number"),
    (re.compile(r"^```"), "code_block"),
    (re.compile(r"<table", re.IGNORECASE), "table"),
    (re.compile(r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b"), "date"),
    (re.compile(r"\b\d+(?:\.\d+)?(?:%|万|亿|元)\b"), "number"),
    (re.compile(r"#+\s+"), "heading"),
]


def _parse_line_index(path: str, total_lines: int) -> int | None:
    """Extract line index from path like /lines/5 or /content/3. Returns None if invalid."""
    parts = path.strip("/").split("/")
    if len(parts) < 2:
        return None
    try:
        idx = int(parts[-1])
        if 0 <= idx < total_lines:
            return idx
    except ValueError:
        pass
    return None


def _is_protected(line: str) -> str | None:
    """Check if a line contains protected content. Returns reason or None."""
    for pattern, reason in PROTECTED_PATTERNS:
        if pattern.search(line):
            return reason
    return None


def run(data: dict) -> None:
    target_md_path = data["target_md_path"]
    patch_ops = data["patch"]
    max_delete_ratio = data.get("max_delete_ratio", 0.3)

    warnings: list[str] = []
    rejected: list[dict] = []

    target_p = Path(target_md_path)
    if not target_p.exists():
        fail("KBPREP_INVALID_INPUT", f"target_md_path does not exist: {target_md_path}")

    source_text = target_p.read_text(encoding="utf-8")
    lines = source_text.split("\n")
    total_chars = len(source_text)

    # Validate each op
    delete_count = 0
    validated_ops: list[dict] = []

    for op in patch_ops:
        op_type = op.get("op")
        path = op.get("path", "")

        if op_type == "remove":
            idx = _parse_line_index(path, len(lines))
            if idx is not None:
                reason = _is_protected(lines[idx])
                if reason:
                    rejected.append({"op": json.dumps(op), "reason": f"protected_{reason}"})
                    continue
            delete_count += 1

        elif op_type in ("replace", "add"):
            value = str(op.get("value", ""))
            idx = _parse_line_index(path, len(lines))
            # Reject if value looks like summarization (very short replacement for content)
            if len(value) < 20 and idx is not None and "/content" in path:
                rejected.append({"op": json.dumps(op), "reason": "possible_summarization"})
                continue
            # Reject if replacing a protected line with very different content
            if op_type == "replace" and idx is not None:
                reason = _is_protected(lines[idx])
                if reason and len(value) < len(lines[idx]) * 0.3:
                    rejected.append({"op": json.dumps(op), "reason": f"protected_{reason}_rewrite"})
                    continue

        validated_ops.append(op)

    # Check total delete ratio
    if total_chars > 0:
        delete_ratio = delete_count / max(len(lines), 1)
        if delete_ratio > max_delete_ratio:
            fail("KBPREP_PATCH_REJECTED",
                 f"Patch deletes {delete_ratio:.0%} of content, exceeding max_delete_ratio {max_delete_ratio:.0%}",
                 details={"delete_ratio": delete_ratio, "max_delete_ratio": max_delete_ratio})

    # Apply validated ops
    working_lines = list(lines)
    applied = 0

    # Sort ops: process in reverse line order for remove/replace to avoid index shifting
    # But 'add' ops need forward order. Simplest: apply one at a time with index adjustment.
    for op in validated_ops:
        op_type = op.get("op")
        path = op.get("path", "")
        idx = _parse_line_index(path, len(working_lines))

        if idx is None:
            warnings.append(f"Could not parse path: {path}")
            continue

        if op_type == "remove":
            if 0 <= idx < len(working_lines):
                working_lines.pop(idx)
                applied += 1

        elif op_type == "replace":
            value = str(op.get("value", ""))
            if 0 <= idx < len(working_lines):
                working_lines[idx] = value
                applied += 1

        elif op_type == "add":
            value = str(op.get("value", ""))
            if 0 <= idx <= len(working_lines):
                working_lines.insert(idx, value)
                applied += 1

    # Write patched file
    output_path = target_p.parent / (target_p.stem + ".patched" + target_p.suffix)
    output_path.write_text("\n".join(working_lines), encoding="utf-8")

    ok(data={
        "ok": True,
        "applied": applied,
        "rejected": rejected,
        "output_path": str(output_path),
    }, warnings=warnings)
