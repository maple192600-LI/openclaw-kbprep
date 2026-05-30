"""Lightweight text-layer PDF conversion.

This converter is intentionally narrow: it only uses an existing, trusted PDF
text layer. OCR, image-heavy, and garbled PDFs stay on the MinerU route.
"""

import json
import re
from pathlib import Path


def convert_text_layer_pdf(input_path: Path, output_path: Path, run_dir: Path) -> dict:
    """Extract readable Markdown from a trusted PDF text layer.

    Returns a MinerU-shaped artifact dict so downstream page mapping, block
    ranges, and conversion reports can keep working without special cases.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError as e:
        raise RuntimeError("PyMuPDF is required for pdf_text_layer conversion") from e

    doc = fitz.open(str(input_path))
    content_list: list[dict] = []
    markdown_parts: list[str] = []

    try:
        for page_idx, page in enumerate(doc):
            text = page.get_text("text").strip()
            if not text:
                continue

            normalized = _normalize_page_text(text)
            if not normalized:
                continue

            markdown_parts.append(f"<!-- page: {page_idx + 1} -->\n\n{normalized}")
            content_list.append({
                "type": "text",
                "page_idx": page_idx,
                "text": normalized,
            })
    finally:
        doc.close()

    markdown = "\n\n".join(markdown_parts).strip()
    if not markdown:
        raise RuntimeError(f"{input_path.name} has no extractable trusted text layer")

    output_path.write_text(markdown + "\n", encoding="utf-8")
    content_list_path = run_dir / "pdf_text_content_list.json"
    content_list_path.write_text(
        json.dumps(content_list, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "source_md_path": str(output_path),
        "content_list_path": str(content_list_path),
        "content_list_v2_path": None,
        "middle_json_path": None,
        "assets_dir": None,
        "converter": "pdf_text_layer",
        "warnings": [
            "W_PDF_TEXT_LAYER_CONVERTER_USED: used existing PDF text layer; OCR/image layout extraction was skipped."
        ],
    }


def _normalize_page_text(text: str) -> str:
    lines = [line.strip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    cleaned: list[str] = []
    blank_pending = False

    for line in lines:
        if not line:
            blank_pending = bool(cleaned)
            continue
        if blank_pending and cleaned[-1] != "":
            cleaned.append("")
        elif cleaned and _should_merge_hard_wrap(cleaned[-1], line):
            cleaned[-1] = _merge_wrapped_lines(cleaned[-1], line)
            blank_pending = False
            continue
        cleaned.append(line)
        blank_pending = False

    return "\n".join(cleaned).strip()


_STRUCTURAL_LINE_RE = re.compile(
    r"^\s*(?:#{1,6}\s+|[-*+]\s+|\d+[.)、]\s+|>\s*|```|<!--|---\s*$|\|.*\|)"
)
_SENTENCE_END_RE = re.compile(r"[。！？!?；;：:]\s*$")
_CJK_RE = re.compile(r"[\u3400-\u9fff]")


def _should_merge_hard_wrap(previous: str, current: str) -> bool:
    """Join PDF text-layer hard wraps inside paragraphs while preserving structure."""
    prev = previous.strip()
    cur = current.strip()
    if not prev or not cur:
        return False
    if _STRUCTURAL_LINE_RE.match(prev) or _STRUCTURAL_LINE_RE.match(cur):
        return False
    if _SENTENCE_END_RE.search(prev):
        return False
    if len(prev) <= 20 and len(cur) <= 20 and not _SENTENCE_END_RE.search(cur):
        return False
    return bool(_CJK_RE.search(prev[-1]) or _CJK_RE.search(cur[0]))


def _merge_wrapped_lines(previous: str, current: str) -> str:
    if _CJK_RE.search(previous[-1]) or _CJK_RE.search(current[0]):
        return previous.rstrip() + current.lstrip()
    return previous.rstrip() + " " + current.lstrip()
