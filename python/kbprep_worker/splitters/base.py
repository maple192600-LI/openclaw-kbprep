"""
base — splitter interface and shared data types.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from abc import ABC, abstractmethod


@dataclass
class ChunkInfo:
    chunk_id: str = "0001"
    heading_path: list[str] = field(default_factory=list)
    page_start: int | None = None
    page_end: int | None = None
    char_count: int = 0
    protected_blocks: list[str] = field(default_factory=list)
    source_hash: str = ""
    text: str = ""


@dataclass
class SplitResult:
    chunks: list[ChunkInfo] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class SplitConfig:
    target_chars: int = 3500
    max_chars: int = 6000
    min_chars: int = 800
    duplicate_overlap: bool = False


class Splitter(ABC):
    @abstractmethod
    def split(self, source_md: str, content_list: list[dict] | None, config: SplitConfig) -> SplitResult:
        ...


# ── Protected block detection ─────────────────────────────────────

import re

CODE_BLOCK_RE = re.compile(r"^```[\s\S]*?^```", re.MULTILINE)
TABLE_RE = re.compile(r"^<table[\s\S]*?</table>", re.MULTILINE | re.IGNORECASE)
STEP_RE = re.compile(r"^\s*(\d+)[\.\)]\s+", re.MULTILINE)


def find_protected_blocks(text: str) -> list[tuple[int, int, str]]:
    """Find spans that must not be split through. Returns (start, end, type)."""
    blocks: list[tuple[int, int, str]] = []
    for m in CODE_BLOCK_RE.finditer(text):
        blocks.append((m.start(), m.end(), "code_block"))
    for m in TABLE_RE.finditer(text):
        blocks.append((m.start(), m.end(), "table"))
    # Numbered step sequences (3+ consecutive steps)
    lines = text.split("\n")
    offset = 0
    step_start = None
    step_count = 0
    for i, line in enumerate(lines):
        if STEP_RE.match(line.strip()):
            if step_start is None:
                step_start = offset
            step_count += 1
        else:
            if step_count >= 3:
                blocks.append((step_start, offset, "steps"))
            step_start = None
            step_count = 0
        offset += len(line) + 1
    if step_count >= 3 and step_start is not None:
        blocks.append((step_start, offset, "steps"))
    return blocks


def is_in_protected(pos: int, blocks: list[tuple[int, int, str]]) -> bool:
    return any(s <= pos < e for s, e, _ in blocks)
