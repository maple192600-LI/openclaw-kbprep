"""
markdown_note splitter — for Obsidian notes, personal notes, manually curated content.
Priority: YAML frontmatter (keep in source.md, not in chunks) > H1 > H2 > H3 > callout > list tree > paragraph.
Never split a list tree across chunks.
"""
from __future__ import annotations
import hashlib
import re
from .base import Splitter, SplitResult, SplitConfig, ChunkInfo, find_protected_blocks

H_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
CALLOUT_RE = re.compile(r"^>\s*\[!(\w+)\]", re.MULTILINE)
LIST_RE = re.compile(r"^(\s*[-*+]\s|\s*\d+\.\s)", re.MULTILINE)
FRONTMATTER_RE = re.compile(r"^---\n[\s\S]*?\n---\n", re.MULTILINE)


class MarkdownNoteSplitter(Splitter):
    def split(self, source_md: str, content_list: list[dict] | None, config: SplitConfig) -> SplitResult:
        result = SplitResult()

        # Strip frontmatter (keep in source.md, not in chunks)
        fm_match = FRONTMATTER_RE.match(source_md)
        body = source_md[fm_match.end():] if fm_match else source_md

        # Find headings
        headings: list[tuple[int, int, str, str]] = []
        for m in H_RE.finditer(body):
            level = len(m.group(1))
            headings.append((m.start(), level, m.group(2).strip(), m.group(0)))
        headings.sort(key=lambda x: x[0])

        # Build sections
        sections: list[tuple[int, int, list[str]]] = []
        for i, (offset, level, title, _) in enumerate(headings):
            end = len(body)
            for j in range(i + 1, len(headings)):
                if headings[j][1] <= level:
                    end = headings[j][0]
                    break
            path: list[str] = []
            for _, hlevel, htitle, _ in headings[:i + 1]:
                if hlevel <= level:
                    if len(path) >= hlevel:
                        path = path[:hlevel - 1]
                    path.append(htitle)
            sections.append((offset, end, path))

        if not sections:
            sections = [(0, len(body), [])]

        # Split each section
        chunks_data: list[tuple[str, list[str]]] = []
        for sec_start, sec_end, heading_path in sections:
            text = body[sec_start:sec_end].strip()
            if not text:
                continue
            if len(text) <= config.max_chars:
                chunks_data.append((text, heading_path))
            else:
                sub = self._split_note_section(text, config)
                for s in sub:
                    chunks_data.append((s, heading_path))

        # Build final chunks
        final_chunks: list[ChunkInfo] = []
        for i, (text, heading_path) in enumerate(chunks_data):
            text = text.strip()
            if not text:
                continue
            chunk_id = f"{i + 1:04d}"
            source_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
            final_chunks.append(ChunkInfo(
                chunk_id=chunk_id,
                heading_path=heading_path,
                char_count=len(text),
                source_hash=source_hash,
                text=text,
            ))

        result.chunks = final_chunks
        return result

    def _split_note_section(self, text: str, config: SplitConfig) -> list[str]:
        """Split a note section, keeping list trees intact."""
        # Split by double newline but track list groups
        blocks: list[str] = []
        current_block = ""
        in_list = False

        for line in text.split("\n"):
            is_list_line = bool(LIST_RE.match(line))
            is_empty = not line.strip()

            if is_list_line:
                if not in_list and current_block.strip():
                    blocks.append(current_block)
                    current_block = ""
                in_list = True
                current_block += line + "\n"
            elif in_list and is_empty:
                # End of list
                current_block += line + "\n"
                blocks.append(current_block)
                current_block = ""
                in_list = False
            elif in_list and not is_list_line and line.strip() and not line.startswith(" "):
                # Non-indented non-list line — end of list
                blocks.append(current_block)
                current_block = line + "\n"
                in_list = False
            else:
                if in_list:
                    current_block += line + "\n"
                else:
                    if is_empty and current_block.strip():
                        blocks.append(current_block)
                        current_block = ""
                    else:
                        current_block += line + "\n"

        if current_block.strip():
            blocks.append(current_block)

        # Merge blocks into chunks respecting size limits
        chunks: list[str] = []
        current = ""
        for block in blocks:
            candidate = (current + "\n" + block).strip() if current else block.strip()
            if len(candidate) > config.max_chars and current:
                chunks.append(current)
                current = block.strip()
            else:
                current = candidate
            if len(current) >= config.target_chars:
                chunks.append(current)
                current = ""

        if current.strip():
            chunks.append(current)

        return chunks
