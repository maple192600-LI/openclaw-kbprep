"""
blockify - block-level structuring.
Parses normalized.md into structured blocks with metadata.

Input: normalized.md + page map + image map + heading map
Output: blocks.jsonl (list of block dicts)
"""
import hashlib
import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Block types ───────────────────────────────────────────────────
BLOCK_TYPES = [
    "cover", "toc", "marketing_cta", "qr_image", "sales_page",
    "community_benefit", "refund_policy", "author_intro", "testimonial",
    "revenue_claim", "section_heading", "paragraph", "concept",
    "case_intro", "case_step", "operation_step", "tool_instruction",
    "prompt", "code", "table", "image_operation", "image_evidence",
    "diagram", "quote", "warning", "footer", "garbled_text",
    "duplicate", "unknown_review",
]

# ── Heading patterns ──────────────────────────────────────────────
H_RE = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)

# ── Image reference pattern ───────────────────────────────────────
IMG_RE = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')

# ── Code block pattern ────────────────────────────────────────────
CODE_BLOCK_RE = re.compile(r'^```[\s\S]*?^```', re.MULTILINE)

# ── Table pattern (Markdown) ──────────────────────────────────────
TABLE_RE = re.compile(r'^\|.+\|$\n^\|[\s\-:|]+\|$\n(?:^\|.+\|$\n?)+', re.MULTILINE)

# ── Step pattern ──────────────────────────────────────────────────
STEP_RE = re.compile(
    r'^\s*(?:\d+[\.\)、)]\s+|第?[一二三四五六七八九十百千\d]+步[骤]?[：:、\.\s]|步骤\s*[一二三四五六七八九十百千\d]+[：:、\.\s])',
    re.MULTILINE,
)

# ── Quote/callout pattern ─────────────────────────────────────────
EN_STEP_RE = re.compile(r'^\s*step\s*\d+[\uff1a:\.\)\-\s]+', re.MULTILINE | re.IGNORECASE)
CALLOUT_RE = re.compile(r'^>\s*\[!(\w+)\]', re.MULTILINE)


def blockify(text: str, source_hash: str, mineru_artifacts: dict = None, run_dir: str = "") -> list[dict]:
    """
    Parse normalized markdown into structured blocks.
    Each block has: block_id, source_sha256, page_start, page_end,
    line_start, line_end, heading_path, type, text, images, status,
    risk_tags, protected, confidence.
    """
    blocks = []
    lines = text.split("\n")

    # Build page map from MinerU artifacts if available
    page_map = _build_page_map(text, mineru_artifacts)

    # Track heading path
    heading_path: list[str] = []
    heading_stack: list[tuple[int, str]] = []  # (level, title)

    # Split into logical blocks
    current_block_lines: list[str] = []
    current_block_start = 0
    current_heading_path: list[str] = []
    block_idx = 0

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Blank lines separate natural paragraphs. This keeps a tutorial step
        # from being glued to a later CTA or footer block.
        if not stripped:
            if current_block_lines:
                block = _make_block(
                    block_idx, "\n".join(current_block_lines), current_block_start,
                    i - 1, current_heading_path, source_hash, page_map
                )
                if block:
                    blocks.append(block)
                    block_idx += 1
                current_block_lines = []
            current_block_start = i + 1
            i += 1
            continue

        # Check for heading
        h_match = H_RE.match(line)
        if h_match:
            # Flush current block
            if current_block_lines:
                block = _make_block(
                    block_idx, "\n".join(current_block_lines), current_block_start,
                    i - 1, current_heading_path, source_hash, page_map
                )
                if block:
                    blocks.append(block)
                    block_idx += 1
                current_block_lines = []

            # Update heading path
            level = len(h_match.group(1))
            title = h_match.group(2).strip()

            # Pop headings of same or lower level
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, title))
            current_heading_path = [h[1] for h in heading_stack]

            # Add heading as its own block
            block = _make_block(
                block_idx, line, i, i, current_heading_path, source_hash, page_map,
                override_type="section_heading"
            )
            if block:
                blocks.append(block)
                block_idx += 1

            current_block_start = i + 1
            i += 1
            continue

        # Check for code block
        if stripped.startswith("```"):
            # Find end of code block
            code_lines = [line]
            j = i + 1
            while j < len(lines):
                code_lines.append(lines[j])
                if lines[j].strip().startswith("```") and j > i:
                    break
                j += 1

            # Flush current block first
            if current_block_lines:
                block = _make_block(
                    block_idx, "\n".join(current_block_lines), current_block_start,
                    i - 1, current_heading_path, source_hash, page_map
                )
                if block:
                    blocks.append(block)
                    block_idx += 1
                current_block_lines = []

            # Add code block
            code_text = "\n".join(code_lines)
            block = _make_block(
                block_idx, code_text, i, j, current_heading_path, source_hash, page_map,
                override_type="code", protected=True
            )
            if block:
                blocks.append(block)
                block_idx += 1

            i = j + 1
            current_block_start = i
            continue

        # Check for Markdown table
        if stripped.startswith("|") and "|" in stripped[1:]:
            table_lines = [line]
            j = i + 1
            while j < len(lines) and lines[j].strip().startswith("|"):
                table_lines.append(lines[j])
                j += 1

            if len(table_lines) >= 2:  # At least header + separator
                # Flush current block first
                if current_block_lines:
                    block = _make_block(
                        block_idx, "\n".join(current_block_lines), current_block_start,
                        i - 1, current_heading_path, source_hash, page_map
                    )
                    if block:
                        blocks.append(block)
                        block_idx += 1
                    current_block_lines = []

                table_text = "\n".join(table_lines)
                block = _make_block(
                    block_idx, table_text, i, j - 1, current_heading_path, source_hash, page_map,
                    override_type="table", protected=True
                )
                if block:
                    blocks.append(block)
                    block_idx += 1

                i = j
                current_block_start = i
                continue

        # Check for image reference
        img_match = IMG_RE.search(stripped)
        if img_match and len(stripped) < 200:  # Likely a standalone image line
            # Flush current block first
            if current_block_lines:
                block = _make_block(
                    block_idx, "\n".join(current_block_lines), current_block_start,
                    i - 1, current_heading_path, source_hash, page_map
                )
                if block:
                    blocks.append(block)
                    block_idx += 1
                current_block_lines = []

            block = _make_block(
                block_idx, line, i, i, current_heading_path, source_hash, page_map,
                override_type="image_evidence"
            )
            if block:
                blocks.append(block)
                block_idx += 1

            i += 1
            current_block_start = i
            continue

        # Check for callout/quote
        if stripped.startswith(">"):
            # Collect callout lines
            callout_lines = [line]
            j = i + 1
            while j < len(lines) and (lines[j].strip().startswith(">") or lines[j].strip() == ""):
                if lines[j].strip() == "" and j + 1 < len(lines) and not lines[j + 1].strip().startswith(">"):
                    break
                callout_lines.append(lines[j])
                j += 1

            # Flush current block first
            if current_block_lines:
                block = _make_block(
                    block_idx, "\n".join(current_block_lines), current_block_start,
                    i - 1, current_heading_path, source_hash, page_map
                )
                if block:
                    blocks.append(block)
                    block_idx += 1
                current_block_lines = []

            callout_text = "\n".join(callout_lines)
            block = _make_block(
                block_idx, callout_text, i, j - 1, current_heading_path, source_hash, page_map,
                override_type="quote"
            )
            if block:
                blocks.append(block)
                block_idx += 1

            i = j
            current_block_start = i
            continue

        # Regular line — accumulate
        current_block_lines.append(line)
        i += 1

    # Flush remaining block
    if current_block_lines:
        block = _make_block(
            block_idx, "\n".join(current_block_lines), current_block_start,
            len(lines) - 1, current_heading_path, source_hash, page_map
        )
        if block:
            blocks.append(block)

    return blocks


def _make_block(
    idx: int,
    text: str,
    line_start: int,
    line_end: int,
    heading_path: list[str],
    source_hash: str,
    page_map: list[dict],
    override_type: str = None,
    protected: bool = False,
) -> dict | None:
    """Create a block dict from text content."""
    text = text.strip()
    if not text:
        return None

    # Determine block type
    if override_type:
        block_type = override_type
    else:
        block_type = _infer_block_type(text)

    # Find page range
    page_start, page_end = _find_page_range(line_start, line_end, page_map)

    # Extract images
    images = []
    for m in IMG_RE.finditer(text):
        images.append({"alt": m.group(1), "src": m.group(2)})

    block_id = f"b_{idx:06d}"

    return {
        "block_id": block_id,
        "source_sha256": source_hash[:16],
        "page_start": page_start,
        "page_end": page_end,
        "line_start": line_start,
        "line_end": line_end,
        "heading_path": heading_path,
        "type": block_type,
        "text": text,
        "images": images,
        "status": "unclassified",
        "risk_tags": [],
        "protected": protected,
        "confidence": 0.0,
    }


def _infer_block_type(text: str) -> str:
    """Infer block type from content."""
    stripped = text.strip()

    # Code block
    if stripped.startswith("```"):
        return "code"

    # Table
    if stripped.startswith("|"):
        return "table"

    # Heading
    if H_RE.match(stripped):
        return "section_heading"

    # Image
    if IMG_RE.match(stripped) and len(stripped) < 200:
        return "image_evidence"

    # Callout/quote
    if stripped.startswith(">"):
        return "quote"

    # Numbered steps
    if STEP_RE.match(stripped) or EN_STEP_RE.match(stripped):
        return "operation_step"

    # Default
    return "paragraph"


def _build_page_map(text: str, mineru_artifacts: dict = None) -> list[dict]:
    """Build page boundary map from MinerU content_list."""
    if not mineru_artifacts:
        return []

    content_list_path = mineru_artifacts.get("content_list_path")
    if not content_list_path:
        return []

    try:
        content_list = json.loads(Path(content_list_path).read_text(encoding="utf-8"))
        line_offsets = _line_start_offsets(text)
        pages = []
        for item in content_list:
            page_idx = item.get("page_idx", item.get("page", 0))
            item_text = item.get("text", "")
            if item_text:
                pos = text.find(item_text[:40])
                if pos >= 0:
                    pages.append({"page": page_idx, "line": _offset_to_line(pos, line_offsets)})
        pages.sort(key=lambda x: x["line"])
        return pages
    except Exception:
        return []


def _find_page_range(line_start: int, line_end: int, page_map: list[dict]) -> tuple[int | None, int | None]:
    """Find page range for given line positions."""
    if not page_map:
        return None, None

    page_start = None
    page_end = None
    for pm in page_map:
        if pm["line"] <= line_start:
            page_start = pm["page"]
        if pm["line"] <= line_end:
            page_end = pm["page"]

    return page_start, page_end


def _line_start_offsets(text: str) -> list[int]:
    offsets = [0]
    for match in re.finditer(r"\n", text):
        offsets.append(match.end())
    return offsets


def _offset_to_line(offset: int, line_offsets: list[int]) -> int:
    line = 0
    for idx, start in enumerate(line_offsets):
        if start > offset:
            break
        line = idx
    return line
