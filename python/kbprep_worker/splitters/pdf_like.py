"""
pdf_like splitter — for PDF, ebook, long document, MinerU Markdown.
Priority: H1 > H2 > H3 > content_list page blocks > paragraphs > max-length fallback.
"""
from __future__ import annotations
import hashlib
import re
from .base import Splitter, SplitResult, SplitConfig, ChunkInfo, find_protected_blocks, is_in_protected

H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
H2_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)
H3_RE = re.compile(r"^###\s+(.+)$", re.MULTILINE)


class PdfLikeSplitter(Splitter):
    def split(self, source_md: str, content_list: list[dict] | None, config: SplitConfig) -> SplitResult:
        result = SplitResult()
        protected = find_protected_blocks(source_md)

        # Build page boundaries from content_list if available
        page_offsets: list[tuple[int, int]] = []
        if content_list:
            page_offsets = self._build_page_offsets(source_md, content_list)

        # Find all heading positions with their levels
        headings: list[tuple[int, int, str, str]] = []  # (offset, level, title, line)
        for m in H1_RE.finditer(source_md):
            headings.append((m.start(), 1, m.group(1).strip(), m.group(0)))
        for m in H2_RE.finditer(source_md):
            headings.append((m.start(), 2, m.group(1).strip(), m.group(0)))
        for m in H3_RE.finditer(source_md):
            headings.append((m.start(), 3, m.group(1).strip(), m.group(0)))
        headings.sort(key=lambda x: x[0])

        # Build section boundaries
        sections: list[tuple[int, int, list[str]]] = []
        for i, (offset, level, title, _) in enumerate(headings):
            # Find end: next heading of same or higher level, or end of document
            end = len(source_md)
            for j in range(i + 1, len(headings)):
                if headings[j][1] <= level:
                    end = headings[j][0]
                    break
            # Build heading path
            path: list[str] = []
            for _, hlevel, htitle, _ in headings[:i + 1]:
                if hlevel <= level:
                    if len(path) >= hlevel:
                        path = path[:hlevel - 1]
                    path.append(htitle)
            sections.append((offset, end, path))

        # If no headings found, treat entire doc as one section
        if not sections:
            sections = [(0, len(source_md), [])]

        # Split sections into chunks
        chunks: list[tuple[str, list[str], int | None, int | None]] = []  # (text, heading_path, page_start, page_end)

        for sec_start, sec_end, heading_path in sections:
            text = source_md[sec_start:sec_end]
            page_s, page_e = self._find_page_range(sec_start, sec_end, page_offsets)

            if len(text) <= config.max_chars:
                chunks.append((text, heading_path, page_s, page_e))
            else:
                # Split by paragraphs
                sub_chunks = self._split_by_paragraphs(text, config, protected, sec_start)
                for sc in sub_chunks:
                    chunks.append((sc, heading_path, page_s, page_e))

        # Build final chunk list with IDs
        final_chunks: list[ChunkInfo] = []
        for i, (text, heading_path, page_s, page_e) in enumerate(chunks):
            text = text.strip()
            if not text:
                continue
            chunk_id = f"{i + 1:04d}"
            source_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
            info = ChunkInfo(
                chunk_id=chunk_id,
                heading_path=heading_path,
                page_start=page_s,
                page_end=page_e,
                char_count=len(text),
                source_hash=source_hash,
                text=text,
            )
            final_chunks.append(info)

        result.chunks = final_chunks
        return result

    def _split_by_paragraphs(self, text: str, config: SplitConfig, protected: list, base_offset: int) -> list[str]:
        """Split text into chunks respecting paragraph boundaries and protected blocks."""
        paragraphs = re.split(r"\n{2,}", text)
        chunks: list[str] = []
        current = ""

        for para in paragraphs:
            candidate = (current + "\n\n" + para).strip() if current else para.strip()

            if len(candidate) > config.max_chars and current:
                # Would exceed max, flush current
                chunks.append(current)
                current = para.strip()
            elif len(candidate) > config.max_chars and not current:
                # Single paragraph exceeds max_chars — forced split by lines
                lines = para.split("\n")
                current_line_chunk = ""
                for line in lines:
                    lc = (current_line_chunk + "\n" + line).strip() if current_line_chunk else line.strip()
                    if len(lc) > config.max_chars and current_line_chunk:
                        chunks.append(current_line_chunk)
                        current_line_chunk = line.strip()
                    else:
                        current_line_chunk = lc
                if current_line_chunk:
                    current = current_line_chunk
                else:
                    current = ""
            else:
                current = candidate

            if len(current) >= config.target_chars:
                chunks.append(current)
                current = ""

        if current.strip():
            chunks.append(current)

        return chunks

    def _build_page_offsets(self, source_md: str, content_list: list[dict]) -> list[tuple[int, int]]:
        """Estimate page boundaries from content_list."""
        pages: list[tuple[int, int]] = []
        for item in content_list:
            page_idx = item.get("page_idx", item.get("page", 0))
            text = item.get("text", "")
            if not text:
                continue
            pos = source_md.find(text[:40])
            if pos >= 0:
                pages.append((page_idx, pos))
        pages.sort(key=lambda x: x[1])

        boundaries: list[tuple[int, int]] = []
        for i, (pg, start) in enumerate(pages):
            end = pages[i + 1][1] if i + 1 < len(pages) else len(source_md)
            boundaries.append((start, end))
        return boundaries

    def _find_page_range(self, start: int, end: int, page_offsets: list[tuple[int, int]]) -> tuple[int | None, int | None]:
        if not page_offsets:
            return None, None
        page_start = None
        page_end = None
        for i, (ps, pe) in enumerate(page_offsets):
            if ps <= start < pe or (page_start is None and ps >= start):
                page_start = i + 1
            if ps < end:
                page_end = i + 1
        return page_start, page_end
