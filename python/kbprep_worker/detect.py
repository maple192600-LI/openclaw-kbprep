"""
detect — source type detection based on file extension and content.
"""
from pathlib import Path

from .supported_formats import (
    AUDIO_EXTENSIONS as SHARED_AUDIO_EXTENSIONS,
    SOURCE_TYPE_BY_EXTENSION,
    SUBTITLE_EXTENSIONS,
    VIDEO_EXTENSIONS as SHARED_VIDEO_EXTENSIONS,
)

# Extension → default source_type mapping
EXTENSION_MAP: dict[str, str] = {
    ".pdf": "pdf_like",
    ".epub": "pdf_like",
    ".mobi": "pdf_like",
    ".docx": "pdf_like",
    ".doc": "pdf_like",
    ".pptx": "generic_block",
    ".ppt": "generic_block",
    ".xlsx": "pdf_like",
    ".xls": "pdf_like",
    ".md": "markdown_note",
    ".markdown": "markdown_note",
    ".txt": "generic_block",
    ".rst": "generic_block",
    ".adoc": "generic_block",
    ".html": "generic_block",
    ".htm": "generic_block",
    ".json": "generic_block",
    ".csv": "generic_block",
    ".tsv": "generic_block",
    ".vtt": "subtitle_transcript",
    ".srt": "subtitle_transcript",
    ".ass": "subtitle_transcript",
    ".lrc": "subtitle_transcript",
    ".mp3": "generic_block",
    ".wav": "generic_block",
    ".m4a": "generic_block",
    ".aac": "generic_block",
    ".flac": "generic_block",
    ".mp4": "generic_block",
    ".mov": "generic_block",
    ".mkv": "generic_block",
    ".webm": "generic_block",
    ".png": "pdf_like",
    ".jpg": "pdf_like",
    ".jpeg": "pdf_like",
    ".bmp": "pdf_like",
    ".tiff": "pdf_like",
    ".tif": "pdf_like",
    ".webp": "pdf_like",
    ".gif": "pdf_like",
}

TEXT_EXTENSIONS = {".md", ".markdown", ".txt", ".rst", ".adoc", ".csv", ".tsv", ".vtt", ".srt", ".ass", ".lrc"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}

EXTENSION_MAP = SOURCE_TYPE_BY_EXTENSION
TEXT_EXTENSIONS = {
    ".md", ".markdown", ".txt", ".rst", ".adoc", ".csv", ".tsv",
    ".html", ".htm", ".json", *SUBTITLE_EXTENSIONS,
}
AUDIO_EXTENSIONS = SHARED_AUDIO_EXTENSIONS
VIDEO_EXTENSIONS = SHARED_VIDEO_EXTENSIONS


def detect_source_type(file_path: str) -> str:
    """Detect source_type from file extension. Returns one of pdf_like, markdown_note, generic_block."""
    ext = Path(file_path).suffix.lower()
    return EXTENSION_MAP.get(ext, "generic_block")


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
    if ext in {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp", ".gif"}:
        return "image"
    if ext in AUDIO_EXTENSIONS:
        return "audio"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    if ext in {".vtt", ".srt", ".ass", ".lrc"}:
        return "subtitle_transcript"
    if ext in TEXT_EXTENSIONS:
        return "text"
    return "unknown"


def detect_language(file_path: str) -> str:
    """Default language hint. Can be overridden by caller."""
    return "ch"
