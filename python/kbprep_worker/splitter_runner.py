"""
splitter_runner — entry point for the split command.
"""
import json
import logging
from pathlib import Path

from .envelope import ok, fail
from .splitters import get_splitter
from .splitters.base import SplitConfig

logger = logging.getLogger(__name__)


def run(data: dict) -> None:
    source_md_path = data["source_md_path"]
    content_list_path = data.get("content_list_path")
    source_type = data["source_type"]
    target_chars = data.get("target_chars", 3500)
    max_chars = data.get("max_chars", 6000)

    warnings: list[str] = []
    source_p = Path(source_md_path)

    if not source_p.exists():
        fail("KBPREP_INVALID_INPUT", f"source_md_path does not exist: {source_md_path}")

    # Read source
    source_md = source_p.read_text(encoding="utf-8")

    # Read content_list if provided
    content_list = None
    if content_list_path:
        cl_p = Path(content_list_path)
        if cl_p.exists():
            try:
                content_list = json.loads(cl_p.read_text(encoding="utf-8"))
            except Exception as e:
                warnings.append(f"Could not parse content_list: {e}")

    # Get splitter
    try:
        splitter = get_splitter(source_type)
    except ValueError as e:
        fail("KBPREP_INVALID_INPUT", str(e))

    config = SplitConfig(target_chars=target_chars, max_chars=max_chars)

    try:
        result = splitter.split(source_md, content_list, config)
        warnings.extend(result.warnings)
    except Exception as e:
        logger.exception("Split failed")
        fail("KBPREP_SPLIT_FAILED", str(e))

    n = len(result.chunks)
    if n == 0:
        fail("KBPREP_SPLIT_FAILED", "Splitter produced zero chunks.")

    # Write chunks to disk using actual text from splitter
    parent_dir = source_p.parent
    chunks_dir = parent_dir / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)

    for i, chunk_info in enumerate(result.chunks):
        text = chunk_info.text.strip()
        if not text:
            continue

        frontmatter = f"""---
chunk_id: "{chunk_info.chunk_id}"
source_type: {source_type}
heading_path: {json.dumps(chunk_info.heading_path, ensure_ascii=False)}
page_start: {json.dumps(chunk_info.page_start)}
page_end: {json.dumps(chunk_info.page_end)}
char_count: {len(text)}
source_hash: "{chunk_info.source_hash}"
previous_chunk: {json.dumps(result.chunks[i - 1].chunk_id if i > 0 else None)}
next_chunk: {json.dumps(result.chunks[i + 1].chunk_id if i < n - 1 else None)}
---

"""
        chunk_file = chunks_dir / f"{chunk_info.chunk_id}.md"
        chunk_file.write_text(frontmatter + text, encoding="utf-8")

    # Write chunks.jsonl
    index_file = parent_dir / "chunks.jsonl"
    with open(index_file, "w", encoding="utf-8") as f:
        for chunk_info in result.chunks:
            entry = {
                "chunk_id": chunk_info.chunk_id,
                "heading_path": chunk_info.heading_path,
                "page_start": chunk_info.page_start,
                "page_end": chunk_info.page_end,
                "char_count": chunk_info.char_count,
                "source_hash": chunk_info.source_hash,
            }
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    ok(data={
        "chunks_dir": str(chunks_dir),
        "chunks_index": str(index_file),
        "chunk_count": len(result.chunks),
        "warnings": warnings,
    }, warnings=warnings)
