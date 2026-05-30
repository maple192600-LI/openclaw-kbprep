"""
generic_block splitter — fallback for PPT, transcript, social media, repo docs.
v0.1: basic paragraph-based splitting with warning.
v0.2: specialized splitters for ppt_slide, transcript_timestamp, repo_docs, social_post.
"""
from __future__ import annotations
import hashlib
import re
from .base import Splitter, SplitResult, SplitConfig, ChunkInfo


class GenericBlockSplitter(Splitter):
    def split(self, source_md: str, content_list: list[dict] | None, config: SplitConfig) -> SplitResult:
        result = SplitResult()
        result.warnings.append("KBPREP_GENERIC_SPLITTER_USED: specialized splitter not implemented in v0.1")

        # Basic paragraph-based splitting
        paragraphs = re.split(r"\n{2,}", source_md)
        chunks_data: list[str] = []
        current = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            candidate = (current + "\n\n" + para).strip() if current else para
            if len(candidate) > config.max_chars and current:
                chunks_data.append(current)
                current = para
            else:
                current = candidate
            if len(current) >= config.target_chars:
                chunks_data.append(current)
                current = ""

        if current.strip():
            chunks_data.append(current)

        final_chunks: list[ChunkInfo] = []
        for i, text in enumerate(chunks_data):
            text = text.strip()
            if not text:
                continue
            chunk_id = f"{i + 1:04d}"
            source_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
            final_chunks.append(ChunkInfo(
                chunk_id=chunk_id,
                char_count=len(text),
                source_hash=source_hash,
                text=text,
            ))

        result.chunks = final_chunks
        return result
