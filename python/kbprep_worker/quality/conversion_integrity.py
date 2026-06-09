"""Conversion integrity checks for quality reports."""

from pathlib import Path

from .io import _read_json_file
from .markdown_signals import (
    _contains_normalized,
    _extract_image_sources,
    _markdown_headings,
    _markdown_table_count,
    _normalize_heading_text,
    _strip_fenced_code,
)

TEXT_SOURCE_INTEGRITY_EXTENSIONS = {".md", ".markdown", ".txt", ".rst", ".adoc"}

def _source_text_layer_status(diagnosis: dict, conversion_report: dict) -> dict:
    text_quality = diagnosis.get("text_quality", {})
    converter = str(conversion_report.get("converter") or "")
    superseded = _conversion_supersedes_source_text_layer(diagnosis, conversion_report)
    return {
        "text_layer_health": diagnosis.get("text_layer_health"),
        "pdf_subtype": diagnosis.get("pdf_subtype"),
        "needs_ocr": bool(diagnosis.get("needs_ocr")),
        "converter": converter,
        "superseded_by_conversion": superseded,
        "garbled_ratio": text_quality.get("garbled_ratio", 0),
        "unreadable_text_ratio": text_quality.get("unreadable_text_ratio", 0),
        "mojibake_ratio": text_quality.get("mojibake_ratio", 0),
    }

def _conversion_supersedes_source_text_layer(diagnosis: dict, conversion_report: dict) -> bool:
    converter = str(conversion_report.get("converter") or "")
    converted_bytes = int(conversion_report.get("converted_bytes") or 0)
    if converter not in {"mineru", "mineru_after_pdf_text_layer_fallback"}:
        return False
    if converted_bytes <= 0:
        return False
    return bool(
        diagnosis.get("needs_ocr")
        or diagnosis.get("pdf_subtype") == "garbled_text_layer"
        or diagnosis.get("text_layer_health") in {"bad", "untrusted"}
    )

def _converted_text_quality(conversion_report: dict) -> dict:
    artifacts = conversion_report.get("mineru_artifacts")
    if not isinstance(artifacts, dict):
        return {}
    quality = artifacts.get("post_convert_text_quality")
    return quality if isinstance(quality, dict) else {}

def _source_conversion_integrity(run_p: Path, conversion_report: dict) -> dict:
    metadata = _read_json_file(run_p / "run_metadata.json")
    input_path = Path(str(metadata.get("input_path") or ""))
    converted_path = Path(str(conversion_report.get("converted_md") or run_p / "converted.md"))
    input_extension = str(conversion_report.get("input_extension") or input_path.suffix).lower()
    converter = str(conversion_report.get("converter") or "")
    if input_extension not in TEXT_SOURCE_INTEGRITY_EXTENSIONS:
        return _empty_source_conversion_integrity(
            checked=False,
            reason=f"source extension {input_extension or '<none>'} is not a direct text integrity target",
            input_path=str(input_path) if str(input_path) else "",
            converter=converter,
        )
    if not input_path.exists():
        return _empty_source_conversion_integrity(
            checked=False,
            reason="source file not found",
            input_path=str(input_path),
            converter=converter,
        )
    if not converted_path.exists():
        return _empty_source_conversion_integrity(
            checked=False,
            reason="converted.md not found",
            input_path=str(input_path),
            converter=converter,
        )

    source_text = input_path.read_text(encoding="utf-8", errors="replace")
    converted_text = converted_path.read_text(encoding="utf-8", errors="replace")
    source_non_code = _strip_fenced_code(source_text)
    converted_non_code = _strip_fenced_code(converted_text)
    source_headings = _markdown_headings(source_non_code)
    converted_headings = _markdown_headings(converted_non_code)
    missing_headings = [
        heading for heading in source_headings
        if heading and not _contains_normalized(converted_headings, heading)
    ]
    source_tables = _markdown_table_count(source_non_code)
    converted_tables = _markdown_table_count(converted_non_code)
    source_code_blocks = source_text.count("```") // 2
    converted_code_blocks = converted_text.count("```") // 2
    source_image_refs = len(_extract_image_sources(source_non_code))
    converted_image_refs = len(_extract_image_sources(converted_non_code))
    return {
        "checked": True,
        "input_path": str(input_path),
        "input_extension": input_extension,
        "converter": converter,
        "source_headings": len(source_headings),
        "converted_headings": len(converted_headings),
        "missing_heading_count": len(missing_headings),
        "missing_headings": missing_headings[:50],
        "source_tables": source_tables,
        "converted_tables": converted_tables,
        "missing_table_count": max(0, source_tables - converted_tables),
        "source_code_blocks": source_code_blocks,
        "converted_code_blocks": converted_code_blocks,
        "missing_code_block_count": max(0, source_code_blocks - converted_code_blocks),
        "source_image_refs": source_image_refs,
        "converted_image_refs": converted_image_refs,
        "missing_image_ref_count": max(0, source_image_refs - converted_image_refs),
    }

def _empty_source_conversion_integrity(checked: bool, reason: str, input_path: str, converter: str) -> dict:
    return {
        "checked": checked,
        "reason": reason,
        "input_path": input_path,
        "converter": converter,
        "source_headings": 0,
        "converted_headings": 0,
        "missing_heading_count": 0,
        "missing_headings": [],
        "source_tables": 0,
        "converted_tables": 0,
        "missing_table_count": 0,
        "source_code_blocks": 0,
        "converted_code_blocks": 0,
        "missing_code_block_count": 0,
        "source_image_refs": 0,
        "converted_image_refs": 0,
        "missing_image_ref_count": 0,
    }

def _conversion_structure_integrity(blocks: list[dict], run_p: Path) -> dict:
    converted_path = run_p / "converted.md"
    if not converted_path.exists():
        return {
            "checked": False,
            "reason": "converted.md not found",
            "converted_headings": 0,
            "block_headings": 0,
            "missing_heading_count": 0,
            "missing_headings": [],
            "converted_tables": 0,
            "block_tables": 0,
            "missing_table_count": 0,
            "converted_code_blocks": 0,
            "block_code_blocks": 0,
            "missing_code_block_count": 0,
            "converted_image_refs": 0,
            "block_image_refs": 0,
            "missing_image_ref_count": 0,
        }

    converted_text = converted_path.read_text(encoding="utf-8", errors="replace")
    non_code_text = _strip_fenced_code(converted_text)
    converted_headings = _markdown_headings(non_code_text)
    block_text = "\n\n".join(str(block.get("text", "")) for block in blocks)
    block_non_code_text = _strip_fenced_code(block_text)
    block_headings = [
        _normalize_heading_text(str(block.get("text", "")))
        for block in blocks
        if block.get("type") == "section_heading"
    ]
    block_headings.extend(_markdown_headings(block_non_code_text))
    missing_headings = [
        heading for heading in converted_headings
        if heading and not _contains_normalized(block_headings, heading)
    ]

    converted_tables = _markdown_table_count(non_code_text)
    block_tables = max(sum(1 for block in blocks if block.get("type") == "table"), _markdown_table_count(block_non_code_text))
    converted_code_blocks = converted_text.count("```") // 2
    block_code_blocks = max(sum(1 for block in blocks if block.get("type") == "code"), block_text.count("```") // 2)
    converted_image_refs = len(_extract_image_sources(non_code_text))
    block_image_refs = len(_extract_image_sources(block_non_code_text))

    return {
        "checked": True,
        "converted_headings": len(converted_headings),
        "block_headings": len([heading for heading in block_headings if heading]),
        "missing_heading_count": len(missing_headings),
        "missing_headings": missing_headings[:50],
        "converted_tables": converted_tables,
        "block_tables": block_tables,
        "missing_table_count": max(0, converted_tables - block_tables),
        "converted_code_blocks": converted_code_blocks,
        "block_code_blocks": block_code_blocks,
        "missing_code_block_count": max(0, converted_code_blocks - block_code_blocks),
        "converted_image_refs": converted_image_refs,
        "block_image_refs": block_image_refs,
        "missing_image_ref_count": max(0, converted_image_refs - block_image_refs),
    }
