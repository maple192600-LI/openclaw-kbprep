"""
split_v4 — v4 block-aware splitting.
Splits blocks into Obsidian-manageable chunks with full traceability.

Supports: pdf_like, markdown_note, generic_block splitters.
"""
import hashlib
import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Chunk size limits ─────────────────────────────────────────────
CHUNK_MIN_CHARS = 300
CHUNK_TARGET_CHARS = 1200
CHUNK_MAX_CHARS = 3500


def split_into_chunks(
    blocks: list[dict],
    run_dir: str,
    source_type: str,
    source_hash: str,
    run_id: str,
    split_strategy: str | None = None,
) -> dict:
    """
    Split kept blocks into chunks.
    Returns dict with chunk_count, warnings.
    """
    warnings = []

    # Select splitter
    if split_strategy == "preserve_slide_or_page_order":
        chunks = _split_by_page_order(blocks)
    elif source_type == "pdf_like":
        chunks = _split_pdf_like(blocks)
    elif source_type == "markdown_note":
        chunks = _split_markdown_note(blocks)
    elif source_type == "subtitle_transcript":
        chunks = _split_transcript(blocks)
    else:
        chunks = _split_generic(blocks)
        warnings.append("W_GENERIC_SPLITTER_USED: specialized splitter not available for this source type")

    # Filter out empty chunks
    chunks = [c for c in chunks if c.get("text", "").strip()]

    if not chunks:
        return {"chunk_count": 0, "warnings": warnings + ["No chunks produced"]}

    # Write chunks
    run_p = Path(run_dir)
    chunks_dir = run_p / "chunks"
    chunks_dir.mkdir(exist_ok=True)

    manifest_entries = []

    for i, chunk in enumerate(chunks):
        chunk_id = f"chunk_{i + 1:04d}"
        text = chunk.get("text", "").strip()
        if not text:
            continue

        # Build frontmatter
        heading_path = chunk.get("heading_path", [])
        block_ids = chunk.get("block_ids", [])
        page_start = chunk.get("page_start")
        page_end = chunk.get("page_end")
        source_type_str = source_type
        split_strategy_str = split_strategy or "content_structure"

        frontmatter = f"""---
chunk_id: "{chunk_id}"
source_type: {source_type_str}
split_strategy: {split_strategy_str}
source_sha256: "{source_hash[:16]}"
run_id: "{run_id}"
page_range: {json.dumps(f"{page_start}-{page_end}" if page_start is not None and page_end is not None else "unknown")}
heading_path: {json.dumps(heading_path, ensure_ascii=False)}
block_ids: {json.dumps(block_ids, ensure_ascii=False)}
char_count: {len(text)}
---

"""
        chunk_file = chunks_dir / f"{chunk_id}.md"
        chunk_file.write_text(frontmatter + text, encoding="utf-8")

        manifest_entries.append({
            "chunk_id": chunk_id,
            "heading_path": heading_path,
            "block_ids": block_ids,
            "page_start": page_start,
            "page_end": page_end,
            "char_count": len(text),
            "split_strategy": split_strategy_str,
        })

    # Write chunk_manifest.jsonl
    manifest_path = run_p / "chunk_manifest.jsonl"
    with open(manifest_path, "w", encoding="utf-8") as f:
        for entry in manifest_entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return {
        "chunk_count": len(manifest_entries),
        "warnings": warnings,
    }


def _split_pdf_like(blocks: list[dict]) -> list[dict]:
    """
    Split PDF-like content by H1/H2/H3 headings, then by block type.
    Priority: H1 > H2 > H3 > block type > page range.
    """
    chunks = []
    current_chunk = _new_chunk()

    for block in blocks:
        if block.get("status") != "keep":
            continue

        block_type = block.get("type", "")
        text = block.get("text", "").strip()
        if not text:
            continue

        # Heading blocks start new chunks
        if block_type == "section_heading":
            current_text = current_chunk.get("text", "").strip()
            if current_text and len(current_text) >= CHUNK_MIN_CHARS:
                chunks.append(current_chunk)
                current_chunk = _new_chunk()
                current_chunk["heading_path"] = block.get("heading_path", [])
            elif current_text:
                # Small chunk: merge heading into current
                pass

        # Check if adding this block would exceed max
        candidate_text = current_chunk.get("text", "") + "\n\n" + text if current_chunk.get("text") else text
        if len(candidate_text) > CHUNK_MAX_CHARS and current_chunk.get("text", "").strip():
            # Flush current chunk if it's big enough
            if len(current_chunk.get("text", "")) >= CHUNK_MIN_CHARS:
                chunks.append(current_chunk)
                current_chunk = _new_chunk()
                current_chunk["heading_path"] = block.get("heading_path", [])

        # Add block to current chunk
        if current_chunk.get("text"):
            current_chunk["text"] += "\n\n" + text
        else:
            current_chunk["text"] = text

        current_chunk["block_ids"].append(block.get("block_id", ""))

        # Update page range
        ps = block.get("page_start")
        pe = block.get("page_end")
        if ps is not None:
            if current_chunk["page_start"] is None or ps < current_chunk["page_start"]:
                current_chunk["page_start"] = ps
        if pe is not None:
            if current_chunk["page_end"] is None or pe > current_chunk["page_end"]:
                current_chunk["page_end"] = pe

        # Check if we've reached target size
        if len(current_chunk.get("text", "")) >= CHUNK_TARGET_CHARS:
            chunks.append(current_chunk)
            current_chunk = _new_chunk()

    # Flush remaining
    if current_chunk.get("text", "").strip():
        chunks.append(current_chunk)

    return chunks


def _split_by_page_order(blocks: list[dict]) -> list[dict]:
    """
    Preserve page/slide boundaries for slide decks and sparse landscape reports.
    This is only used when diagnosis explicitly requests slide/page order.
    """
    chunks = []
    current_chunk = _new_chunk()
    current_page = None

    for block in blocks:
        if block.get("status") != "keep":
            continue

        text = block.get("text", "").strip()
        if not text:
            continue

        ps = block.get("page_start")
        pe = block.get("page_end")
        block_page = ps if ps is not None else current_page
        candidate_text = current_chunk.get("text", "") + "\n\n" + text if current_chunk.get("text") else text

        page_changed = (
            current_chunk.get("text", "").strip()
            and current_page is not None
            and block_page is not None
            and block_page != current_page
        )
        too_large = len(candidate_text) > CHUNK_MAX_CHARS and current_chunk.get("text", "").strip()

        if page_changed or too_large:
            chunks.append(current_chunk)
            current_chunk = _new_chunk()

        if current_chunk.get("text"):
            current_chunk["text"] += "\n\n" + text
        else:
            current_chunk["text"] = text

        current_chunk["block_ids"].append(block.get("block_id", ""))
        if block.get("heading_path") and not current_chunk.get("heading_path"):
            current_chunk["heading_path"] = block["heading_path"]

        if ps is not None:
            if current_chunk["page_start"] is None or ps < current_chunk["page_start"]:
                current_chunk["page_start"] = ps
            current_page = ps
        if pe is not None:
            if current_chunk["page_end"] is None or pe > current_chunk["page_end"]:
                current_chunk["page_end"] = pe
            if current_page is None:
                current_page = pe

    if current_chunk.get("text", "").strip():
        chunks.append(current_chunk)

    return chunks


def _split_markdown_note(blocks: list[dict]) -> list[dict]:
    """
    Split Markdown notes by H1/H2/H3 headings.
    Preserves YAML frontmatter, Obsidian links, tags, callouts.
    """
    # For markdown notes, splitting is similar to pdf_like but more conservative
    return _split_pdf_like(blocks)


def _split_generic(blocks: list[dict]) -> list[dict]:
    """
    Generic splitter: aggregate blocks by order, 1000-2000 chars per chunk.
    Preserves code blocks, tables, and prompts as whole units.
    """
    chunks = []
    current_chunk = _new_chunk()

    for block in blocks:
        if block.get("status") != "keep":
            continue

        text = block.get("text", "").strip()
        if not text:
            continue

        block_type = block.get("type", "")

        # Protected blocks stay together
        if block.get("protected") or block_type in ("code", "table", "prompt"):
            # If current chunk + this block exceeds max, flush first
            candidate = current_chunk.get("text", "") + "\n\n" + text if current_chunk.get("text") else text
            if len(candidate) > CHUNK_MAX_CHARS and current_chunk.get("text", "").strip():
                chunks.append(current_chunk)
                current_chunk = _new_chunk()

        # Check size
        candidate = current_chunk.get("text", "") + "\n\n" + text if current_chunk.get("text") else text
        if len(candidate) > CHUNK_TARGET_CHARS and current_chunk.get("text", "").strip():
            chunks.append(current_chunk)
            current_chunk = _new_chunk()

        # Add to chunk
        if current_chunk.get("text"):
            current_chunk["text"] += "\n\n" + text
        else:
            current_chunk["text"] = text
        current_chunk["block_ids"].append(block.get("block_id", ""))

        # Update heading path
        if block.get("heading_path") and not current_chunk.get("heading_path"):
            current_chunk["heading_path"] = block["heading_path"]

    # Flush remaining
    if current_chunk.get("text", "").strip():
        chunks.append(current_chunk)

    return chunks


def _split_transcript(blocks: list[dict]) -> list[dict]:
    """Split transcripts by paragraph order while preserving utterance order."""
    return _split_generic(blocks)


def _new_chunk() -> dict:
    """Create a new empty chunk dict."""
    return {
        "text": "",
        "heading_path": [],
        "block_ids": [],
        "page_start": None,
        "page_end": None,
    }
