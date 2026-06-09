"""Format-specific non-PDF diagnosis helpers."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

from ..quality.thresholds import DIAGNOSIS_THRESHOLDS
from .text_quality import analyze_text_quality, detect_text_profile


def analyze_markdown(input_path: str, detected_format: str | None = None) -> dict:
    """Analyze text-like files that can be converted without OCR."""
    warnings = []

    if detected_format == "notebook":
        try:
            from ..notebook import notebook_to_markdown
            text = notebook_to_markdown(input_path)
        except Exception as e:
            return {"text_layer_health": "error", "warnings": [f"Cannot parse notebook: {e}"]}
    else:
        try:
            text = Path(input_path).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            for enc in ["utf-8-sig", "gbk", "gb2312", "latin-1"]:
                try:
                    text = Path(input_path).read_text(encoding=enc)
                    warnings.append(f"Encoding: {enc} (not UTF-8)")
                    break
                except (UnicodeDecodeError, LookupError):
                    continue
            else:
                return {"text_layer_health": "error", "warnings": ["Cannot decode file"]}

    ext = Path(input_path).suffix.lower()
    profile_input = _text_for_profile(text, detected_format or "text")
    quality = analyze_text_quality(profile_input)

    # Count headings
    heading_re = re.compile(r'^#{1,6}\s+', re.MULTILINE)
    heading_count = len(heading_re.findall(profile_input))

    # Count code blocks
    code_block_re = re.compile(r'^```[\s\S]*?^```', re.MULTILINE)
    code_block_count = len(code_block_re.findall(profile_input))

    # Count tables
    table_re = re.compile(r'^\|.+\|$', re.MULTILINE)
    table_row_count = len(table_re.findall(profile_input))

    profile_format = detected_format or ("markdown" if ext in {".md", ".markdown"} else "text")

    result = {
        "page_count": 1,
        "total_text_length": len(profile_input),
        "heading_count": heading_count,
        "code_block_count": code_block_count,
        "table_row_count": table_row_count,
        "text_quality": quality,
        "text_layer_health": "good",
        "needs_ocr": False,
        "recommended_pipeline": "direct",
        **detect_text_profile(profile_input, profile_format),
    }
    if detected_format == "code":
        result["conversion_strategy"] = "direct_code"
    elif detected_format == "notebook":
        result["conversion_strategy"] = "notebook_json"

    if quality["garbled_ratio"] > DIAGNOSIS_THRESHOLDS["markdown_garbled_warn"]:
        result["text_layer_health"] = "degraded"
        warnings.append(f"High garbled ratio: {quality['garbled_ratio']:.2%}")

    if quality["ocr_ai_confusion_count"] > 0:
        warnings.append(f"W_OCR_AI_CONFUSION: {quality['ocr_ai_confusion_count']} patterns found")

    result["warnings"] = warnings
    return result


def _text_for_profile(text: str, detected_format: str) -> str:
    if detected_format == "html":
        text = re.sub(r"(?is)<(script|style|nav|footer|header|aside|figure|figcaption|noscript|template)\b[^>]*>.*?</\1>", "\n", text)
        text = re.sub(r"(?is)<br\s*/?>", "\n", text)
        text = re.sub(r"(?is)</(p|div|li|h[1-6]|tr|section|article)>", "\n", text)
        text = re.sub(r"(?is)<[^>]+>", " ", text)
        text = re.sub(r"[ \t]+", " ", text)
    return text


def analyze_audio_video(input_path: str, detected_format: str) -> dict:
    return {
        "page_count": 0,
        "total_text_length": 0,
        "text_layer_health": "unavailable",
        "needs_ocr": False,
        "recommended_pipeline": "provide_transcript_first",
        "text_profile": detected_format,
        "warnings": [
            "Audio/video binary files are not transcribed in v1. Provide a local subtitle, transcript, or ASR text file."
        ],
    }


def analyze_office(input_path: str, detected_format: str) -> dict:
    """Choose the Office conversion route without mutating the input file."""
    modern_office = {"docx", "pptx", "xlsx"}
    if detected_format in modern_office:
        if not zipfile.is_zipfile(input_path):
            return {
                "page_count": 0,
                "text_layer_health": "invalid_container",
                "needs_ocr": False,
                "recommended_pipeline": "office_xml",
                "conversion_strategy": "office_xml",
                "warnings": [f"{detected_format} is not a valid Office Open XML package"],
            }
        return {
            "page_count": 0,
            "text_layer_health": "needs_conversion",
            "needs_ocr": False,
            "recommended_pipeline": "office_xml",
            "conversion_strategy": "office_xml",
            "warnings": [],
        }

    return {
        "page_count": 0,
        "text_layer_health": "external_conversion_required",
        "needs_ocr": False,
        "recommended_pipeline": "external_conversion_required",
        "conversion_strategy": "unsupported_external_conversion_required",
        "warnings": [f"{detected_format} is not supported by KBPrep's verified conversion routes. Convert it to a modern Office XML file, PDF, Markdown, or text first."],
    }


def analyze_ebook(input_path: str, ext: str) -> dict:
    if ext == ".epub":
        try:
            from ..epub import analyze_epub
            return analyze_epub(input_path)
        except Exception as e:
            return {
                "page_count": 0,
                "text_layer_health": "invalid_container",
                "needs_ocr": False,
                "recommended_pipeline": "epub_xhtml",
                "conversion_strategy": "epub_xhtml",
                "warnings": [f"EPUB analysis failed: {e}"],
            }
    return {
        "page_count": 0,
        "text_layer_health": "external_conversion_required",
        "needs_ocr": False,
        "recommended_pipeline": "external_conversion_required",
        "conversion_strategy": "unsupported_external_conversion_required",
        "warnings": ["MOBI is not supported by KBPrep's verified conversion routes. Convert it to EPUB, PDF, Markdown, or text first."],
    }
