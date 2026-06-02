"""
diagnose - file quality diagnosis for kbprep.
Read-only: does not modify any files.

Outputs: file hash, type, page count, text layer health, garbled ratio,
image page ratio, OCR recommendation, and detailed quality metrics.
"""
import hashlib
import json
import logging
import os
import re
import sys
import zipfile
from pathlib import Path

from .envelope import ok, fail
from .supported_formats import FORMAT_BY_EXTENSION, SOURCE_TYPE_BY_FORMAT

logger = logging.getLogger(__name__)

EXTENSION_MAP = FORMAT_BY_EXTENSION
SOURCE_TYPE_MAP = SOURCE_TYPE_BY_FORMAT

# Chinese character range
CJK_RE = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf\U00020000-\U0002a6df]')
# English letters and digits
ALNUM_RE = re.compile(r'[a-zA-Z0-9]')
# Control characters (excluding common whitespace)
CONTROL_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]')
COMMON_CJK_RE = re.compile(r'[\u4e00-\u9fff]')
COMMON_NON_CJK_RE = re.compile(r'[a-zA-Z0-9\s\u3000-\u303f.,;:!?()\-—\[\]{}<>"\'/\\@#$%^&*+=|~`，。！？；：（）【】《》、]')
# Common OCR confusion patterns
OCR_AI_CONFUSION_RE = re.compile(r'\b(?:All in Al|Al编程|Al工具|A时代|Al使用|ClaudeCode|Google Al)\b')
# Garbled text: long runs of non-CJK, non-ASCII, non-common-punctuation
GARBLED_RE = re.compile(r'[^\u4e00-\u9fff\u3000-\u303fa-zA-Z0-9\s.,;:!?()\-—\[\]{}<>"\'/\\@#$%^&*+=|~`]{15,}')
# Common Chinese mojibake produced by broken PDF text layers. These are valid
# Unicode characters, so a plain CJK ratio check can miss them.
MOJIBAKE_RE = re.compile(
    r'(?:[鐩綍绔鍏姝鏄鐨瀹鏂杩鎴搴閰瑙涓叧妯鍙鎶姟鍔卞彂]{2,}|[鈥聽銆€]{1,})'
)
MOJIBAKE_CHAR_RE = re.compile(r'[鐩綍绔鍏姝鏄鐨瀹鏂杩鎴搴閰瑙涓叧妯鍙鎶姟鍔卞彂绯荤粺]')
# QR code indicators in readable text.
QR_TEXT_RE = re.compile(r'(?:扫码|二维码|扫一[扫下]|QR\s*code|qrcode)', re.IGNORECASE)
# CTA indicators in readable text.
CTA_TEXT_RE = re.compile(
    r'(?:扫码(?:加入|入群|进群)|添加.*(?:客服|助理|老师|服务官)|免费领取|体验卡|'
    r'限时优惠|立即购买|立即报名|点击链接|长按识别)',
    re.IGNORECASE,
)


MOJIBAKE_TOKEN_RE = re.compile(
    "|".join(
        re.escape(token)
        for token in [
            "姗欑毊", "鍏ラ棬", "绮鹃€", "娑电洊", "鏋舵瀯", "鍘熺悊", "閮ㄧ讲",
            "鏂规", "妗堛€", "娓犻亾", "鎺ュ叆", "绯荤粺", "妯″瀷", "閰嶇疆",
            "瀹夊叏", "鎴愭湰", "鍙傝€", "鎵嬪唽", "淇℃伅", "鏉ユ簮", "瀹樻柟",
            "鏂囨。", "浠撳簱", "绀惧尯", "璋冪爺", "鐗堟湰", "閫傜敤", "鍙戝竷",
            "鏃堕棿", "鐢熸€", "鍏ㄦ櫙", "鍏紬", "鐭ヨ瘑", "缂栫▼", "杈呭姪",
            "鍑嗙‘", "娆㈣繋", "鍏虫敞", "鍙嶉", "棣堜氦", "閰嶅", "瑙嗛",
        ]
    )
)


def analyze_text_quality(text: str) -> dict:
    """Analyze text quality metrics."""
    if not text:
        return {
            "total_chars": 0,
            "chinese_ratio": 0.0,
            "alnum_ratio": 0.0,
            "control_ratio": 0.0,
            "garbled_ratio": 0.0,
            "garbled_chars": 0,
            "non_common_unicode_ratio": 0.0,
            "replacement_char_ratio": 0.0,
            "mojibake_ratio": 0.0,
            "mojibake_chars": 0,
            "unreadable_text_ratio": 0.0,
            "ocr_ai_confusion_count": 0,
            "has_qr_text": False,
            "has_cta_text": False,
        }

    total = len(text)
    chinese_chars = len(CJK_RE.findall(text))
    alnum_chars = len(ALNUM_RE.findall(text))
    control_chars = len(CONTROL_RE.findall(text))
    garbled_matches = GARBLED_RE.findall(text)
    garbled_chars = sum(len(m) for m in garbled_matches)
    non_common_unicode_chars = sum(
        1
        for ch in text
        if ord(ch) > 127 and not COMMON_CJK_RE.match(ch) and not COMMON_NON_CJK_RE.match(ch)
    )
    replacement_chars = text.count("?") + text.count("\ufffd")
    mojibake_matches = MOJIBAKE_RE.findall(text)
    mojibake_sequence_chars = sum(len(m) for m in mojibake_matches)
    mojibake_char_count = len(MOJIBAKE_CHAR_RE.findall(text))
    mojibake_token_chars = sum(len(m.group(0)) for m in MOJIBAKE_TOKEN_RE.finditer(text))
    mojibake_chars = max(mojibake_sequence_chars, mojibake_char_count, mojibake_token_chars)
    non_common_unicode_ratio = non_common_unicode_chars / total if total > 0 else 0.0
    replacement_char_ratio = replacement_chars / total if total > 0 else 0.0
    mojibake_ratio = mojibake_chars / total if total > 0 else 0.0
    unreadable_text_ratio = max(
        garbled_chars / total if total > 0 else 0.0,
        non_common_unicode_ratio,
        mojibake_ratio,
        replacement_char_ratio if (chinese_chars + alnum_chars) / total < 0.2 else 0.0,
    )
    ocr_confusions = len(OCR_AI_CONFUSION_RE.findall(text))

    return {
        "total_chars": total,
        "chinese_ratio": round(chinese_chars / total, 4) if total > 0 else 0.0,
        "alnum_ratio": round(alnum_chars / total, 4) if total > 0 else 0.0,
        "control_ratio": round(control_chars / total, 4) if total > 0 else 0.0,
        "garbled_ratio": round(garbled_chars / total, 4) if total > 0 else 0.0,
        "garbled_chars": garbled_chars,
        "non_common_unicode_ratio": round(non_common_unicode_ratio, 4),
        "replacement_char_ratio": round(replacement_char_ratio, 4),
        "mojibake_ratio": round(mojibake_ratio, 4),
        "mojibake_chars": mojibake_chars,
        "unreadable_text_ratio": round(unreadable_text_ratio, 4),
        "ocr_ai_confusion_count": ocr_confusions,
        "has_qr_text": bool(QR_TEXT_RE.search(text)),
        "has_cta_text": bool(CTA_TEXT_RE.search(text)),
    }


def detect_text_profile(text: str, detected_format: str = "text") -> dict:
    """Classify text shape without summarizing or rewriting it."""
    headings = len(re.findall(r'^#{1,6}\s+', text, re.MULTILINE))
    numbered_steps = len(re.findall(
        r'^\s*(?:\d+[\.\)、)]\s+|第?[一二三四五六七八九十百千\d]+步[骤]?[：:、\.\s]|步骤\s*[一二三四五六七八九十百千\d]+[：:、\.\s])',
        text,
        re.MULTILINE,
    ))
    english_numbered_steps = len(re.findall(r'^\s*step\s*\d+[\uff1a:\.\)\-\s]+', text, re.MULTILINE | re.IGNORECASE))
    numbered_steps += english_numbered_steps
    timestamp_lines = len(re.findall(r'^\s*(?:\d{1,2}:)?\d{1,2}:\d{2}(?:[.,]\d{1,3})?', text, re.MULTILINE))
    speaker_lines = len(re.findall(r'^\s*[^:\n：]{1,24}[：:]\s+\S+', text, re.MULTILINE))
    table_rows = len(re.findall(r'^\|.+\|$', text, re.MULTILINE))
    chars = len(text)

    tutorial_terms = ["步骤", "操作", "设置", "配置", "教程", "如何", "怎么", "实操", "案例", "prompt", "提示词"]
    meeting_terms = ["会议", "讨论", "主持人", "嘉宾", "提问", "回答", "访谈"]
    note_terms = ["笔记", "复盘", "心得", "思考", "总结"]
    ebook_terms = ["目录", "第一章", "第二章", "前言", "附录"]

    if headings >= 8 and chars > 12_000:
        profile = "ebook_or_long_report"
    elif detected_format == "subtitle_transcript" or timestamp_lines >= 3 or speaker_lines >= 8:
        profile = "transcript"
    elif numbered_steps >= 3 or english_numbered_steps > 0 or any(term.lower() in text.lower() for term in tutorial_terms):
        profile = "tutorial"
    elif any(term in text for term in meeting_terms):
        profile = "meeting_or_interview"
    elif any(term in text for term in note_terms):
        profile = "note"
    elif any(term in text for term in ebook_terms) and chars > 12_000:
        profile = "ebook_or_long_report"
    elif chars < 4_000:
        profile = "short_text"
    else:
        profile = "long_text"

    return {
        "text_profile": profile,
        "char_count": chars,
        "heading_count": headings,
        "numbered_step_count": numbered_steps,
        "timestamp_line_count": timestamp_lines,
        "speaker_line_count": speaker_lines,
        "table_row_count": table_rows,
    }


def analyze_pdf(input_path: str) -> dict:
    """Analyze PDF file quality using PyMuPDF (fitz)."""
    warnings = []
    result = _initial_pdf_result()

    try:
        import fitz  # PyMuPDF
    except ImportError:
        warnings.append("PyMuPDF not installed. PDF analysis limited. Install: pip install pymupdf")
        # Try basic analysis with mineru's content extraction
        result["text_layer_health"] = "unavailable"
        result["warnings"] = warnings
        return result

    try:
        doc = fitz.open(input_path)
        page_stats = _collect_pdf_page_stats(doc)
        total_text = page_stats["total_text"]
        result.update({key: value for key, value in page_stats.items() if key != "total_text"})
        image_pages = page_stats["image_pages"]
        text_pages = page_stats["text_pages"]
        image_count = page_stats["image_count"]
        landscape_pages = page_stats["landscape_pages"]

        quality = analyze_text_quality(total_text)
        result["text_quality"] = quality
        if total_text.strip():
            result.update(detect_text_profile(total_text, "pdf"))

        _apply_text_layer_assessment(result, quality, image_pages, text_pages, warnings)
        _apply_image_ratio_assessment(result, image_pages, text_pages, warnings)
        _append_ocr_confusion_warning(quality, warnings)

        doc.close()

        _apply_pdf_layout_profile(result, image_pages, text_pages, image_count, landscape_pages)
        _apply_pdf_processing_strategy(result)

    except Exception as e:
        warnings.append(f"PDF analysis error: {e}")
        result["text_layer_health"] = "error"

    result["warnings"] = warnings
    return result


def _initial_pdf_result() -> dict:
    return {
        "page_count": 0,
        "image_pages": 0,
        "text_pages": 0,
        "empty_pages": 0,
        "total_text_length": 0,
        "image_count": 0,
        "text_layer_health": "unknown",
        "is_scanned": False,
        "is_garbled": False,
        "needs_ocr": False,
        "recommended_pipeline": "mineru_pipeline",
    }


def _collect_pdf_page_stats(doc) -> dict:
    image_pages = 0
    text_pages = 0
    empty_pages = 0
    total_text = ""
    image_count = 0
    landscape_pages = 0
    max_image_count_on_page = 0

    for page_num in range(len(doc)):
        page = doc[page_num]
        if page.rect.width > page.rect.height:
            landscape_pages += 1
        text = page.get_text("text").strip()
        images = page.get_images(full=True)
        image_count += len(images)
        max_image_count_on_page = max(max_image_count_on_page, len(images))

        if not text and images:
            image_pages += 1
        elif text:
            text_pages += 1
            total_text += text + "\n"
        else:
            empty_pages += 1

    return {
        "page_count": len(doc),
        "image_pages": image_pages,
        "text_pages": text_pages,
        "empty_pages": empty_pages,
        "total_text": total_text,
        "total_text_length": len(total_text),
        "image_count": image_count,
        "landscape_pages": landscape_pages,
        "max_image_count_on_page": max_image_count_on_page,
        "average_text_chars_per_text_page": round(len(total_text) / text_pages, 1) if text_pages else 0,
    }


def _apply_bad_text_layer(result: dict, warnings: list[str], message: str, *, degraded: bool = False) -> None:
    result["text_layer_health"] = "degraded" if degraded else "bad"
    result["pdf_subtype"] = "garbled_text_layer"
    result["needs_ocr"] = True
    result["recommended_pipeline"] = "mineru_pipeline_ocr"
    if not degraded:
        result["is_garbled"] = True
    warnings.append(message)


def _apply_text_layer_assessment(result: dict, quality: dict, image_pages: int, text_pages: int, warnings: list[str]) -> None:
    if text_pages == 0 and image_pages > 0:
        result["text_layer_health"] = "no_text_layer"
        result["pdf_subtype"] = "image_only_or_scanned"
        result["is_scanned"] = True
        result["needs_ocr"] = True
        result["recommended_pipeline"] = "mineru_pipeline_ocr"
    elif quality.get("unreadable_text_ratio", quality["garbled_ratio"]) > 0.25:
        _apply_bad_text_layer(
            result,
            warnings,
            "W_PDF_TEXT_LAYER_UNTRUSTED: "
            f"unreadable text ratio {quality.get('unreadable_text_ratio', 0):.2%}",
        )
    elif quality.get("mojibake_ratio", 0) > 0.08:
        _apply_bad_text_layer(result, warnings, f"W_PDF_TEXT_LAYER_UNTRUSTED: mojibake ratio {quality['mojibake_ratio']:.2%}")
    elif quality["garbled_ratio"] > 0.08:
        _apply_bad_text_layer(result, warnings, f"W_PDF_TEXT_LAYER_UNTRUSTED: garbled ratio {quality['garbled_ratio']:.2%}")
    elif quality.get("mojibake_ratio", 0) > 0.03:
        _apply_bad_text_layer(result, warnings, f"W_PDF_TEXT_LAYER_UNTRUSTED: mojibake ratio {quality['mojibake_ratio']:.2%}", degraded=True)
    elif quality["garbled_ratio"] > 0.03:
        _apply_bad_text_layer(result, warnings, f"W_PDF_TEXT_LAYER_UNTRUSTED: garbled ratio {quality['garbled_ratio']:.2%}", degraded=True)
    elif quality["chinese_ratio"] < 0.05 and result["page_count"] > 5:
        result["text_layer_health"] = "low_content"
        warnings.append("Low Chinese content ratio — may be scanned or non-Chinese document")
    else:
        result["text_layer_health"] = "good"
        result["pdf_subtype"] = "text_layer"


def _apply_image_ratio_assessment(result: dict, image_pages: int, text_pages: int, warnings: list[str]) -> None:
    if result["page_count"] <= 0:
        return
    image_page_ratio = image_pages / result["page_count"]
    result["image_page_ratio"] = round(image_page_ratio, 4)
    if image_page_ratio > 0.5:
        result["needs_ocr"] = True
        result["pdf_subtype"] = "image_heavy_mixed" if text_pages else "image_only_or_scanned"
        if result["recommended_pipeline"] == "mineru_pipeline":
            result["recommended_pipeline"] = "mineru_pipeline_ocr"
            warnings.append(f"W_FORCE_OCR_RECOMMENDED: {image_page_ratio:.0%} pages are image-only")


def _append_ocr_confusion_warning(quality: dict, warnings: list[str]) -> None:
    if quality["ocr_ai_confusion_count"] > 0:
        warnings.append(f"W_OCR_AI_CONFUSION: {quality['ocr_ai_confusion_count']} AI/Al confusion patterns found")


def _apply_pdf_layout_profile(
    result: dict,
    image_pages: int,
    text_pages: int,
    image_count: int,
    landscape_pages: int,
) -> None:
    if result["page_count"] > 0 and image_pages > 0 and text_pages > 0 and "pdf_subtype" not in result:
        result["pdf_subtype"] = "mixed_text_image"
    landscape_ratio = landscape_pages / result["page_count"] if result["page_count"] else 0
    result["landscape_ratio"] = round(landscape_ratio, 4)

    avg_chars = result["average_text_chars_per_text_page"]
    slide_like_score = 0.0
    if result["page_count"] >= 3:
        if landscape_ratio >= 0.8:
            slide_like_score += 0.45
        if avg_chars and avg_chars < 900:
            slide_like_score += 0.25
        if image_count >= result["page_count"]:
            slide_like_score += 0.2
        if text_pages <= max(1, result["page_count"] * 0.25):
            slide_like_score += 0.1
    result["slide_like_score"] = round(min(slide_like_score, 1.0), 4)

    if result["slide_like_score"] >= 0.65:
        result["layout_profile"] = "slide_deck_or_ppt_export"
    elif landscape_ratio >= 0.8:
        result["layout_profile"] = "landscape_report"
    elif image_pages / result["page_count"] > 0.5 if result["page_count"] else False:
        result["layout_profile"] = "image_heavy_document"
    else:
        result["layout_profile"] = "document_pages"

    if (
        image_count >= result["page_count"]
        and text_pages <= max(1, result["page_count"] * 0.2)
        and landscape_ratio > 0.5
    ):
        result["pdf_subtype"] = "ppt_exported_or_scanned"
    elif (
        result.get("pdf_subtype") == "text_layer"
        and result["layout_profile"] == "slide_deck_or_ppt_export"
    ):
        result["pdf_subtype"] = "ppt_exported_text_layer"


def _apply_pdf_processing_strategy(result: dict) -> None:
    pdf_subtype = result.get("pdf_subtype", "unknown")
    layout_profile = result.get("layout_profile", "unknown")
    hints: list[str] = []

    if result.get("needs_ocr"):
        result["recommended_pipeline"] = "mineru_pipeline_ocr"
        result["conversion_strategy"] = "mineru_ocr"
        hints.append("Run OCR because the text layer is missing, image-heavy, or untrusted.")
    elif pdf_subtype == "ppt_exported_text_layer":
        result["recommended_pipeline"] = "pdf_text_layer"
        result["conversion_strategy"] = "pdf_text_layer_slide_order"
        result["split_strategy"] = "preserve_slide_or_page_order"
        hints.append("Use the text layer but preserve slide/page order; do not treat this like a dense ebook.")
    elif pdf_subtype == "mixed_text_image":
        result["recommended_pipeline"] = "mineru_pipeline"
        result["conversion_strategy"] = "mineru_mixed_text_image"
        hints.append("Keep both extracted text and image evidence; review image-heavy blocks before deletion.")
    else:
        result["recommended_pipeline"] = "pdf_text_layer"
        result["conversion_strategy"] = "pdf_text_layer"
        hints.append("Use the existing text layer; OCR is not recommended by diagnosis.")

    if "split_strategy" not in result:
        result["split_strategy"] = (
            "preserve_slide_or_page_order"
            if layout_profile == "slide_deck_or_ppt_export"
            else "content_structure"
        )

    if pdf_subtype in {"image_only_or_scanned", "ppt_exported_or_scanned"}:
        hints.append("Expect OCR output; keep discarded text recoverable for manual review.")
    if layout_profile == "slide_deck_or_ppt_export":
        hints.append("Slides and report pages often contain sparse but important details; avoid over-aggressive cleanup.")

    result["processing_hints"] = hints


def analyze_markdown(input_path: str, detected_format: str | None = None) -> dict:
    """Analyze text-like files that can be converted without OCR."""
    warnings = []

    if detected_format == "notebook":
        try:
            from .notebook import notebook_to_markdown
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

    if quality["garbled_ratio"] > 0.05:
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
        "text_layer_health": "needs_conversion",
        "needs_ocr": False,
        "recommended_pipeline": "mineru_pipeline",
        "conversion_strategy": "mineru",
        "warnings": [],
    }


def analyze_ebook(input_path: str, ext: str) -> dict:
    if ext == ".epub":
        try:
            from .epub import analyze_epub
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
        "text_layer_health": "needs_conversion",
        "needs_ocr": False,
        "recommended_pipeline": "mineru_pipeline",
        "conversion_strategy": "mineru",
        "warnings": [],
    }


def run(data: dict) -> None:
    """Entry point for diagnose command."""
    input_path = data["input_path"]
    output_root = data.get("output_root", ".")
    override_source_type = data.get("source_type", "auto")

    input_p = Path(input_path)
    if not input_p.exists():
        fail("E_INPUT_NOT_FOUND", f"Input file does not exist: {input_path}")

    warnings = []

    # File metadata
    file_bytes = input_p.read_bytes()
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    file_size = len(file_bytes)
    ext = input_p.suffix.lower()
    detected_format = EXTENSION_MAP.get(ext, "unknown")

    if detected_format == "unknown":
        fail("E_UNSUPPORTED_TYPE", f"Unsupported file extension: {ext}")

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
        # Legacy Office defaults to MinerU; modern Office Open XML is overridden below.
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
            analysis["conversion_strategy"] = "mineru"
    elif detected_format == "image":
        analysis = {
            "page_count": 1,
            "text_layer_health": "needs_ocr",
            "needs_ocr": True,
            "recommended_pipeline": "mineru_pipeline_ocr",
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
        "needs_ocr": analysis.get("needs_ocr", False),
        "recommended_pipeline": analysis.get("recommended_pipeline", "direct"),
        "warnings": warnings,
        **analysis,
    }
    if not result.get("conversion_strategy"):
        result["conversion_strategy"] = result.get("recommended_pipeline", "direct")

    ok(data=result, warnings=warnings)
