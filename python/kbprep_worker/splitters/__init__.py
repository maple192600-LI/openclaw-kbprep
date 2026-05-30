"""Splitters package."""
from .base import Splitter, SplitResult, ChunkInfo
from .pdf_like import PdfLikeSplitter
from .markdown_note import MarkdownNoteSplitter
from .generic_block import GenericBlockSplitter

SPLITTER_MAP = {
    "pdf_like": PdfLikeSplitter,
    "markdown_note": MarkdownNoteSplitter,
    "generic_block": GenericBlockSplitter,
}

def get_splitter(source_type: str) -> Splitter:
    cls = SPLITTER_MAP.get(source_type)
    if cls is None:
        raise ValueError(f"Unknown source_type: {source_type}")
    return cls()
