"""Runtime-facing diagnose command entry points."""

from __future__ import annotations

import hashlib
from pathlib import Path

from ..converter_capabilities import get_capability_for_extension
from ..envelope import fail, ok
from ..supported_formats import (
    EXTERNAL_CONVERSION_REQUIRED_EXTENSIONS,
    FORMAT_BY_EXTENSION,
    SOURCE_TYPE_BY_FORMAT,
)
from .format_detect import analyze_audio_video, analyze_ebook, analyze_markdown, analyze_office
from .pdf_analysis import analyze_pdf

EXTENSION_MAP = FORMAT_BY_EXTENSION
SOURCE_TYPE_MAP = SOURCE_TYPE_BY_FORMAT


class DiagnoseError(Exception):
    def __init__(self, code: str, message: str, details: dict | None = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


def diagnose_file(data: dict) -> tuple[dict, list[str]]:
    """Analyze one input file and return worker data plus warnings."""
    input_path = data["input_path"]
    output_root = data.get("output_root", ".")
    override_source_type = data.get("source_type", "auto")

    input_p = Path(input_path)
    if not input_p.exists():
        raise DiagnoseError("E_INPUT_NOT_FOUND", f"Input file does not exist: {input_path}")

    warnings = []

    # File metadata
    file_bytes = input_p.read_bytes()
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    file_size = len(file_bytes)
    ext = input_p.suffix.lower()
    detected_format = EXTENSION_MAP.get(ext, "unknown")
    capability = get_capability_for_extension(ext)

    if detected_format == "unknown":
        raise DiagnoseError("E_UNSUPPORTED_TYPE", f"Unsupported file extension: {ext}")
    if ext in EXTERNAL_CONVERSION_REQUIRED_EXTENSIONS:
        warnings.append(
            f"{ext} is not supported by KBPrep's verified conversion routes; convert it to a verified format first."
        )

    # Determine source_type
    if override_source_type and override_source_type != "auto":
        source_type = override_source_type
    else:
        source_type = SOURCE_TYPE_MAP.get(detected_format, "generic_block")

    # Format-specific analysis
    analysis = {}
    if detected_format == "pdf":
        analysis = analyze_pdf(input_path)
        warnings.extend(analysis.pop("warnings", []))
    elif detected_format == "ebook":
        analysis = analyze_ebook(input_path, ext)
        warnings.extend(analysis.pop("warnings", []))
    elif detected_format in ("markdown", "text", "subtitle_transcript", "html", "json", "code", "notebook"):
        analysis = analyze_markdown(input_path, detected_format)
        warnings.extend(analysis.pop("warnings", []))
    elif detected_format in ("audio", "video"):
        analysis = analyze_audio_video(input_path, detected_format)
        warnings.extend(analysis.pop("warnings", []))
    elif detected_format in ("docx", "doc", "xlsx", "xls", "pptx", "ppt"):
        analysis = {
            "page_count": 0,
            "text_layer_health": "needs_conversion",
            "needs_ocr": False,
            "recommended_pipeline": "mineru_pipeline",
        }
        if detected_format in ("docx", "pptx", "xlsx"):
            analysis = analyze_office(input_path, detected_format)
            warnings.extend(analysis.pop("warnings", []))
        else:
            analysis = {
                "page_count": 0,
                "text_layer_health": "external_conversion_required",
                "needs_ocr": False,
                "recommended_pipeline": "external_conversion_required",
                "conversion_strategy": "unsupported_external_conversion_required",
            }
    elif detected_format == "image":
        analysis = {
            "page_count": 1,
            "text_layer_health": "external_conversion_required",
            "needs_ocr": True,
            "recommended_pipeline": "external_conversion_required",
            "conversion_strategy": "unsupported_external_conversion_required",
        }
    else:
        analysis = {
            "page_count": 0,
            "text_layer_health": "unknown",
            "needs_ocr": False,
            "recommended_pipeline": "direct",
        }

    # Build output
    result = {
        "ok": True,
        "file_id": file_hash,
        "file_name": input_p.name,
        "file_size": file_size,
        "detected_format": detected_format,
        "source_type": source_type,
        "capability": capability,
        "needs_ocr": analysis.get("needs_ocr", False),
        "recommended_pipeline": analysis.get("recommended_pipeline", "direct"),
        "warnings": warnings,
        **analysis,
    }
    if not result.get("conversion_strategy"):
        result["conversion_strategy"] = result.get("recommended_pipeline", "direct")

    return result, warnings


def run(data: dict) -> None:
    """Entry point for diagnose command."""
    try:
        result, warnings = diagnose_file(data)
    except DiagnoseError as exc:
        fail(exc.code, exc.message, details=exc.details)
    ok(data=result, warnings=warnings)
