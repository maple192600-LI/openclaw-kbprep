"""Source type detection based on file extension."""
from pathlib import Path

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
    PLAIN_TEXT_EXTENSIONS,
    SOURCE_TYPE_BY_EXTENSION,
    SUBTITLE_EXTENSIONS,
    TABLE_TEXT_EXTENSIONS,
    VIDEO_EXTENSIONS,
)

TEXT_EXTENSIONS = (
    MARKDOWN_EXTENSIONS
    | PLAIN_TEXT_EXTENSIONS
    | TABLE_TEXT_EXTENSIONS
    | HTML_EXTENSIONS
    | JSON_EXTENSIONS
    | SUBTITLE_EXTENSIONS
)
EXTENSION_MAP = SOURCE_TYPE_BY_EXTENSION


def detect_source_type(file_path: str) -> str:
    """Detect processing source_type from file extension."""
    ext = Path(file_path).suffix.lower()
    return SOURCE_TYPE_BY_EXTENSION.get(ext, "generic_block")


def detect_source_family(file_path: str) -> str:
    """Detect the broad input family for diagnostics and routing."""
    ext = Path(file_path).suffix.lower()
    if ext == ".pdf":
        return "pdf"
    if ext in {".docx", ".doc", ".odt"}:
        return "word"
    if ext in {".pptx", ".ppt", ".odp"}:
        return "presentation"
    if ext in {".xlsx", ".xls", ".ods"}:
        return "spreadsheet"
    if ext in EPUB_EXTENSIONS or ext == ".mobi":
        return "ebook"
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in AUDIO_EXTENSIONS:
        return "audio"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    if ext in SUBTITLE_EXTENSIONS:
        return "subtitle_transcript"
    if ext in NOTEBOOK_EXTENSIONS:
        return "notebook"
    if ext in CODE_EXTENSIONS:
        return "code"
    if ext in TEXT_EXTENSIONS:
        return "text"
    if ext in OFFICE_XML_EXTENSIONS | LEGACY_OFFICE_EXTENSIONS:
        return "office"
    return "unknown"


def detect_language(file_path: str) -> str:
    """Default language hint. Can be overridden by caller."""
    return "ch"
