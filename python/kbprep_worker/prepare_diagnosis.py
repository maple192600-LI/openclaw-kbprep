"""Diagnosis report helpers for the single-file prepare pipeline."""

import json
import re
from pathlib import Path

from .supported_formats import (
    DIRECT_EXTENSIONS,
    EPUB_EXTENSIONS,
    FORMAT_BY_EXTENSION,
    HTML_EXTENSIONS,
    MEDIA_EXTENSIONS,
    OFFICE_XML_EXTENSIONS,
)


def write_diagnosis_report(
    run_dir: Path,
    input_path: Path,
    file_hash: str,
    source_type: str,
    diagnosis: dict,
    runtime: dict,
    warnings: list[str],
) -> None:
    fallback = diagnosis_fallback(input_path)
    report = {
        "schema": "kbprep.diagnosis_report.v1",
        "input_file": input_path.name,
        "input_extension": input_path.suffix.lower(),
        "source_sha256": file_hash,
        "source_type": source_type,
        "detected_format": diagnosis.get("detected_format") or fallback["detected_format"],
        "recommended_pipeline": diagnosis.get("recommended_pipeline") or fallback["recommended_pipeline"],
        "conversion_strategy": diagnosis.get("conversion_strategy") or fallback["conversion_strategy"],
        "split_strategy": diagnosis.get("split_strategy"),
        "text_profile": diagnosis.get("text_profile"),
        "text_layer_health": diagnosis.get("text_layer_health"),
        "pdf_subtype": diagnosis.get("pdf_subtype"),
        "layout_profile": diagnosis.get("layout_profile"),
        "slide_like_score": diagnosis.get("slide_like_score"),
        "needs_ocr": diagnosis.get("needs_ocr"),
        "processing_hints": diagnosis.get("processing_hints", []),
        "runtime": runtime,
        "diagnosis": diagnosis,
        "warnings": warnings,
    }
    (run_dir / "diagnosis_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def diagnosis_fallback(input_path: Path) -> dict:
    ext = input_path.suffix.lower()
    detected_format = FORMAT_BY_EXTENSION.get(ext, "unknown")
    if ext in DIRECT_EXTENSIONS:
        strategy = "direct"
    elif ext in OFFICE_XML_EXTENSIONS:
        strategy = "office_xml"
    elif ext in EPUB_EXTENSIONS:
        strategy = "epub_xhtml"
    elif ext in MEDIA_EXTENSIONS:
        strategy = "provide_transcript_first"
    else:
        strategy = "mineru"
    return {
        "detected_format": detected_format,
        "recommended_pipeline": strategy,
        "conversion_strategy": strategy,
    }


def source_title_for_render(input_p: Path, converted_path: Path) -> str:
    if input_p.suffix.lower() in HTML_EXTENSIONS and converted_path.exists():
        try:
            for line in converted_path.read_text(encoding="utf-8").splitlines():
                match = re.match(r"^#\s+(.+?)\s*$", line)
                if match:
                    return match.group(1).strip()
        except Exception:
            pass
    return input_p.stem
