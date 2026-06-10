"""Declared conversion capabilities for KBPrep.

This registry is deliberately conservative: it describes what the current
pipeline routes through, not what every source format can be guaranteed to
preserve perfectly.
"""

from __future__ import annotations

from .supported_formats import (
    AUDIO_EXTENSIONS,
    CODE_EXTENSIONS,
    EPUB_EXTENSIONS,
    HTML_EXTENSIONS,
    IMAGE_EXTENSIONS,
    JSON_EXTENSIONS,
    LEGACY_OFFICE_EXTENSIONS,
    MARKDOWN_EXTENSIONS,
    NOTEBOOK_EXTENSIONS,
    OFFICE_XML_EXTENSIONS,
    PDF_EXTENSIONS,
    PLAIN_TEXT_EXTENSIONS,
    SUBTITLE_EXTENSIONS,
    TABLE_TEXT_EXTENSIONS,
    VIDEO_EXTENSIONS,
)


Capability = dict[str, object]


_CAPABILITIES: tuple[Capability, ...] = (
    {
        "id": "markdown_text_direct",
        "source_type": "markdown_note",
        "extensions": sorted(MARKDOWN_EXTENSIONS | PLAIN_TEXT_EXTENSIONS | TABLE_TEXT_EXTENSIONS),
        "route": "direct_text",
        "dependencies": [],
        "fallback": None,
        "status": "verified",
        "test_evidence": [
            "src/worker.test.ts::declares converter capabilities and exposes the chosen capability through diagnosis",
            "src/worker.test.ts::reports source-to-converted integrity loss for text sources",
        ],
        "preserves": ["headings", "paragraphs", "tables", "links", "code-like details"],
        "risk": "cleanup rules can still remove useful text if rules are too broad",
    },
    {
        "id": "html_direct",
        "source_type": "generic_block",
        "extensions": sorted(HTML_EXTENSIONS),
        "route": "direct_text",
        "dependencies": ["python html.parser"],
        "fallback": None,
        "status": "partial",
        "test_evidence": [
            "src/worker.test.ts::converts local HTML, JSON, and CSV sources into readable Markdown",
        ],
        "required_evidence": [
            "golden HTML fixtures with navigation/footer/cookie noise and body preservation checks",
            "source-to-converted structure comparison for headings, links, images, and lists",
        ],
        "promotion_blocker": "Needs golden fixtures for noisy webpages before this route can be marked verified.",
        "preserves": ["visible text", "headings", "lists", "links", "image references"],
        "risk": "navigation, footer, cookie, and ad wrappers need document-type cleanup rules",
    },
    {
        "id": "json_direct",
        "source_type": "generic_block",
        "extensions": sorted(JSON_EXTENSIONS),
        "route": "direct_text",
        "dependencies": ["python json"],
        "fallback": None,
        "status": "verified",
        "test_evidence": [
            "src/worker.test.ts::converts local HTML, JSON, and CSV sources into readable Markdown",
        ],
        "preserves": ["keys", "values", "nesting where representable in Markdown"],
        "risk": "large machine JSON may be readable but not knowledge-friendly",
    },
    {
        "id": "code_direct",
        "source_type": "generic_block",
        "extensions": sorted(CODE_EXTENSIONS),
        "route": "direct_code",
        "dependencies": [],
        "fallback": None,
        "status": "verified",
        "test_evidence": [
            "src/worker.test.ts::converts GitHub-style source and config files as fenced Markdown without summarizing code",
        ],
        "preserves": ["exact code", "parameters", "comments", "URLs"],
        "risk": "code must be protected from prose cleanup",
    },
    {
        "id": "notebook_json",
        "source_type": "generic_block",
        "extensions": sorted(NOTEBOOK_EXTENSIONS),
        "route": "notebook_json",
        "dependencies": ["python json"],
        "fallback": None,
        "status": "partial",
        "test_evidence": [
            "src/worker.test.ts::converts Jupyter notebooks into readable Markdown cells with code and text outputs",
        ],
        "required_evidence": [
            "golden notebooks with markdown cells, code cells, text outputs, rich display outputs, and attachments",
            "cell-order and output-retention assertions",
        ],
        "promotion_blocker": "Needs notebook fixtures beyond simple text/code cells before this route can be marked verified.",
        "preserves": ["markdown cells", "code cells", "cell order"],
        "risk": "outputs, attachments, and rich display data need more fixtures",
    },
    {
        "id": "subtitle_transcript_direct",
        "source_type": "subtitle_transcript",
        "extensions": sorted(SUBTITLE_EXTENSIONS),
        "route": "direct_text",
        "dependencies": [],
        "fallback": None,
        "status": "verified",
        "test_evidence": [
            "src/worker.test.ts::normalizes local subtitle files into readable transcript markdown",
        ],
        "preserves": ["utterance order", "timestamps when present", "speaker-like lines"],
        "risk": "subtitle noise still needs transcript-specific cleanup",
    },
    {
        "id": "office_xml",
        "source_type": "pdf_like",
        "extensions": sorted(OFFICE_XML_EXTENSIONS),
        "route": "office_xml",
        "dependencies": ["python zipfile", "Office Open XML package structure"],
        "fallback": None,
        "status": "partial",
        "test_evidence": [
            "src/worker.test.ts::converts modern Office files through the local XML fallback when MinerU is unnecessary",
        ],
        "required_evidence": [
            "golden DOCX, PPTX, and XLSX fixtures with headings, tables, slides, sheets, embedded images, and charts",
            "layout-loss and sheet/slide-order assertions",
        ],
        "promotion_blocker": "Needs broader Office XML golden fixtures, especially charts and complex workbooks.",
        "preserves": ["document text", "slide order", "sheet/table text", "embedded images when extractable"],
        "risk": "layout fidelity, charts, and complex workbook semantics are not fully proven",
    },
    {
        "id": "epub_xhtml",
        "source_type": "pdf_like",
        "extensions": sorted(EPUB_EXTENSIONS),
        "route": "epub_xhtml",
        "dependencies": ["python zipfile", "EPUB spine metadata"],
        "fallback": None,
        "status": "partial",
        "test_evidence": [
            "src/worker.test.ts::converts EPUB ebooks through local XHTML extraction instead of MinerU",
        ],
        "required_evidence": [
            "golden EPUB fixtures with footnotes, complex tables, nested XHTML, spine ordering, links, and image assets",
            "chapter-order and footnote/table preservation assertions",
        ],
        "promotion_blocker": "Needs richer EPUB golden fixtures before this route can be marked verified.",
        "preserves": ["spine order", "chapter headings", "links", "images when referenced"],
        "risk": "footnotes, complex tables, and custom XHTML need more fixtures",
    },
    {
        "id": "pdf_diagnosis_selected",
        "source_type": "pdf_like",
        "extensions": sorted(PDF_EXTENSIONS),
        "route": "pdf_diagnosis_selected",
        "dependencies": ["PyMuPDF for diagnosis/text layer", "MinerU/OCR runtime when needed"],
        "fallback": "mineru_ocr when text layer is missing, image-heavy, or rejected",
        "status": "partial",
        "test_evidence": [
            "src/worker.test.ts::converts trusted text-layer PDFs without invoking MinerU",
            "src/worker.test.ts::falls back to MinerU when a trusted PDF text-layer conversion produces unreadable Markdown",
            "src/worker.test.ts::routes image-only scanned PDFs through MinerU OCR and records the actual route",
        ],
        "required_evidence": [
            "golden PDFs covering trusted text layer, scanned/image-only, mixed text-image, PPT exports, tables, images, and OCR fallback",
            "source/converted comparison for chapters, tables, images, page order, and OCR text retention",
        ],
        "promotion_blocker": "Needs a broader PDF golden fixture set across text-layer, scanned, mixed, and layout-heavy PDFs.",
        "preserves": ["page order", "text layer where trusted", "OCR text when routed to MinerU", "image evidence"],
        "risk": "bad embedded text layers and complex layouts require strict quality checks",
    },
    {
        "id": "image_ocr",
        "source_type": "pdf_like",
        "extensions": sorted(IMAGE_EXTENSIONS),
        "route": "external_conversion_required",
        "dependencies": ["MinerU/OCR runtime"],
        "fallback": "Use an external OCR tool first, or place the image inside a PDF with a verified OCR route.",
        "status": "unsupported",
        "test_evidence": [],
        "required_evidence": [
            "standalone image OCR end-to-end fixture using an existing OCR backend",
            "quality gate proving image text is preserved before this route is allowed to write Obsidian output",
        ],
        "promotion_blocker": "Standalone image OCR is unsupported until an existing OCR backend is wired and covered by fixtures.",
        "preserves": [],
        "risk": "Standalone image OCR has no end-to-end KBPrep fixture yet.",
    },
    {
        "id": "legacy_office_or_mobi_heavy_conversion",
        "source_type": "pdf_like",
        "extensions": sorted(LEGACY_OFFICE_EXTENSIONS | {".mobi"}),
        "route": "external_conversion_required",
        "dependencies": ["external Office/MOBI conversion tool"],
        "fallback": "Convert to .docx, .pptx, .xlsx, .epub, .pdf, .md, or .txt before running KBPrep.",
        "status": "unsupported",
        "test_evidence": [],
        "required_evidence": [
            "reliable external conversion fixture for each legacy Office/MOBI family",
            "explicit pre-conversion dependency check and source-to-Markdown integrity evidence",
        ],
        "promotion_blocker": "Legacy Office/MOBI stays unsupported until external conversion is reliable and fixture-backed.",
        "preserves": [],
        "risk": "Legacy Office/MOBI conversion is not verified and should not be silently routed through MinerU.",
    },
    {
        "id": "media_requires_transcript",
        "source_type": "generic_block",
        "extensions": sorted(AUDIO_EXTENSIONS | VIDEO_EXTENSIONS),
        "route": "provide_transcript_first",
        "dependencies": ["external ASR or user-supplied transcript"],
        "fallback": "use .srt, .vtt, .ass, .lrc, .txt, or .md transcript",
        "status": "unsupported",
        "test_evidence": [
            "src/worker.test.ts::declares converter capabilities and exposes the chosen capability through diagnosis",
        ],
        "required_evidence": [
            "external ASR or user-supplied transcript workflow fixtures",
            "tests proving audio/video binaries are not silently treated as readable Markdown",
        ],
        "promotion_blocker": "Audio/video binaries require transcript or ASR integration before KBPrep can process them directly.",
        "preserves": [],
        "risk": "KBPrep v1 does not transcribe audio/video binaries",
    },
)


def capability_matrix_rows() -> list[Capability]:
    return [dict(capability) for capability in _CAPABILITIES]


def capability_gap_report() -> dict:
    gaps = []
    summary = {"verified": 0, "partial": 0, "unsupported": 0, "experimental": 0}
    for capability in _CAPABILITIES:
        status = str(capability.get("status", "unsupported"))
        if status in summary:
            summary[status] += 1
        if status == "verified":
            continue
        gaps.append({
            "id": capability.get("id"),
            "current_status": status,
            "current_route": capability.get("route"),
            "extensions": capability.get("extensions", []),
            "risk": capability.get("risk", ""),
            "promotion_blocker": capability.get("promotion_blocker") or _default_promotion_blocker(capability),
            "required_evidence": capability.get("required_evidence") or _default_required_evidence(capability),
            "test_evidence": capability.get("test_evidence", []),
        })
    return {
        "schema": "kbprep.capability_gap_report.v1",
        "summary": summary,
        "gaps": gaps,
    }


def _default_promotion_blocker(capability: Capability) -> str:
    status = capability.get("status")
    if status == "partial":
        return "Needs broader golden fixtures and preservation checks before being marked verified."
    return "Unsupported until a reliable conversion route and end-to-end fixtures exist."


def _default_required_evidence(capability: Capability) -> list[str]:
    status = capability.get("status")
    if status == "partial":
        return ["golden fixtures", "source-to-Markdown preservation checks"]
    return ["explicit dependency/conversion route", "end-to-end fixture proving safe Markdown output"]


def get_capability_for_extension(extension: str) -> Capability:
    ext = extension.lower()
    for capability in _CAPABILITIES:
        extensions = capability.get("extensions")
        if isinstance(extensions, list) and ext in extensions:
            selected = dict(capability)
            selected["reason"] = f"Extension {ext} matched capability {capability['id']}."
            return selected
    return {
        "id": "unsupported_extension",
        "source_type": "generic_block",
        "extensions": [ext] if ext else [],
        "route": "unsupported",
        "dependencies": [],
        "fallback": None,
        "status": "unsupported",
        "test_evidence": [],
        "preserves": [],
        "risk": "No declared conversion route for this extension.",
        "reason": f"Extension {ext or '<none>'} has no declared KBPrep conversion capability.",
    }
