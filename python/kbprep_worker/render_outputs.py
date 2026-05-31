"""
render_outputs - output rendering from blocks.
Renders: cleaned.md, discarded.md, evidence/, blocks.jsonl (updated).
"""
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def render(blocks: list[dict], run_dir: str, source_hash: str, run_id: str) -> None:
    """
    Render output files from classified blocks.
    - cleaned.md: blocks with status=keep
    - discarded.md: blocks with status=discard
    - evidence/: blocks with status=evidence
    """
    run_p = Path(run_dir)

    # ── Render cleaned.md ─────────────────────────────────────────
    keep_blocks = [b for b in blocks if b.get("status") == "keep"]
    cleaned_lines = []
    for block in keep_blocks:
        text = _readable_text(block)
        if text:
            cleaned_lines.append(text)
    cleaned_md = "\n\n".join(cleaned_lines)
    (run_p / "cleaned.md").write_text(cleaned_md, encoding="utf-8")

    # ── Render discarded.md ───────────────────────────────────────
    discard_blocks = [b for b in blocks if b.get("status") == "discard"]
    discarded_lines = []
    for block in discard_blocks:
        text = block.get("text", "").strip()
        discarded_lines.append(_block_meta_comment(block, include_reason=True))
        if text:
            discarded_lines.append(text)
        discarded_lines.append("")
    discarded_md = "\n".join(discarded_lines)
    (run_p / "discarded.md").write_text(discarded_md, encoding="utf-8")

    # ── Render evidence/ ──────────────────────────────────────────
    evidence_blocks = [b for b in blocks if b.get("status") == "evidence"]
    evidence_dir = run_p / "evidence"
    evidence_dir.mkdir(exist_ok=True)

    if evidence_blocks:
        evidence_lines = []
        for block in evidence_blocks:
            text = block.get("text", "").strip()
            evidence_lines.append(_block_meta_comment(block, include_reason=True))
            if text:
                evidence_lines.append(text)
            evidence_lines.append("")
        evidence_md = "\n".join(evidence_lines)
        (evidence_dir / "marketing_pages.md").write_text(evidence_md, encoding="utf-8")

    # ── Render review blocks (if any) ─────────────────────────────
    review_blocks = [b for b in blocks if b.get("status") == "review"]
    review_path = run_p / "review_needed.md"
    if review_blocks:
        review_lines = []
        for block in review_blocks:
            text = block.get("text", "").strip()
            review_lines.append(_block_meta_comment(block, include_reason=True))
            if text:
                review_lines.append(text)
            review_lines.append("")
        review_md = "\n".join(review_lines)
        review_path.write_text(review_md, encoding="utf-8")
    else:
        review_path.write_text("", encoding="utf-8")

    _render_parts(keep_blocks, run_p)

    logger.info("Rendered: cleaned=%d blocks, discarded=%d, evidence=%d, review=%d",
                len(keep_blocks), len(discard_blocks), len(evidence_blocks), len(review_blocks))


def _render_parts(keep_blocks: list[dict], run_p: Path) -> None:
    """Render long cleaned documents into chapter-aware parts."""
    parts_dir = run_p / "parts"
    parts_dir.mkdir(exist_ok=True)
    for old in parts_dir.glob("part_*.md"):
        old.unlink(missing_ok=True)

    total_chars = sum(len(b.get("text", "")) for b in keep_blocks)
    if total_chars < 12_000:
        return

    parts: list[list[dict]] = []
    current: list[dict] = []
    current_chars = 0
    max_chars = 18_000
    min_chars = 6_000

    for block in keep_blocks:
        text = _readable_text(block)
        if not text:
            continue
        is_heading = block.get("type") == "section_heading"
        if is_heading and current and current_chars >= min_chars:
            parts.append(current)
            current = []
            current_chars = 0
        if current and current_chars + len(text) > max_chars and current_chars >= min_chars:
            parts.append(current)
            current = []
            current_chars = 0
        current.append(block)
        current_chars += len(text)

    if current:
        parts.append(current)

    manifest = []
    for idx, part_blocks in enumerate(parts, start=1):
        part_id = f"part_{idx:03d}"
        part_text = "\n\n".join(_readable_text(b) for b in part_blocks if _readable_text(b))
        heading_path = next((b.get("heading_path", []) for b in part_blocks if b.get("heading_path")), [])
        block_ids = [b.get("block_id") for b in part_blocks]
        content = "\n".join([
            "---",
            f'part_id: "{part_id}"',
            f"heading_path: {json.dumps(heading_path, ensure_ascii=False)}",
            f"block_ids: {json.dumps(block_ids, ensure_ascii=False)}",
            f"char_count: {len(part_text)}",
            "---",
            "",
            part_text,
            "",
        ])
        (parts_dir / f"{part_id}.md").write_text(content, encoding="utf-8")
        manifest.append({
            "part_id": part_id,
            "heading_path": heading_path,
            "block_ids": block_ids,
            "char_count": len(part_text),
        })

    (parts_dir / "parts_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _readable_text(block: dict) -> str:
    """Return text intended for human-readable Markdown outputs."""
    text = block.get("text", "").strip()
    if _is_internal_page_marker(text):
        return ""
    return text


def _block_meta_comment(block: dict, *, include_reason: bool = False) -> str:
    """Render compact trace metadata without changing the recovered source text."""
    pieces = [
        f"[{_comment_safe(str(block.get('block_id') or '?'))}]",
        f"type={_comment_safe(str(block.get('type') or 'unknown'))}",
    ]

    page_start = block.get("page_start")
    page_end = block.get("page_end")
    if page_start is not None or page_end is not None:
        if page_start == page_end:
            pieces.append(f"page={page_start}")
        else:
            pieces.append(f"page={page_start}-{page_end}")

    heading_path = block.get("heading_path")
    if heading_path:
        pieces.append(f"heading={_comment_safe(json.dumps(heading_path, ensure_ascii=False))}")

    risk_tags = block.get("risk_tags")
    if risk_tags:
        pieces.append(f"risk_tags={_comment_safe(json.dumps(risk_tags, ensure_ascii=False))}")

    confidence = block.get("confidence")
    if confidence is not None:
        try:
            pieces.append(f"confidence={float(confidence):.2f}")
        except (TypeError, ValueError):
            pieces.append(f"confidence={_comment_safe(str(confidence))}")

    if include_reason and block.get("reason"):
        pieces.append(f"reason={_comment_safe(str(block.get('reason')))}")

    return f"<!-- {' '.join(pieces)} -->"


def _comment_safe(value: str) -> str:
    return value.replace("--", "- -").replace("\r", " ").replace("\n", " ").strip()


def _is_internal_page_marker(text: str) -> bool:
    return text.strip().lower().startswith("<!-- page:") and text.strip().endswith("-->")
