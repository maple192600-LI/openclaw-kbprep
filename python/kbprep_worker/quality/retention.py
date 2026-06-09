"""Image, detail, and final-output retention checks."""

import re
from pathlib import Path

from .markdown_signals import _extract_image_sources

DETAIL_SIGNAL_PATTERNS = {
    "operation_step": re.compile(
        r"^\s*(?:\d+[\.\)\u3001]\s+|"
        r"step\s*\d+[\uff1a:\.\)\-\s]+|"
        r"\u7b2c[\u4e00-\u9fff\d]+(?:\u6b65|\u6b65\u9aa4)[\uff1a:\u3001\.\s]|"
        r"\u6b65\u9aa4\s*[\u4e00-\u9fff\d]+[\uff1a:\u3001\.\s])",
        re.MULTILINE | re.IGNORECASE,
    ),
    "tool_or_platform": re.compile(
        r"\u5de5\u5177|\u5e73\u53f0|\u8d26\u53f7|\u540e\u53f0|\u7f51\u7ad9|"
        r"\u63d2\u4ef6|APP|API|GitHub|YouTube|Obsidian|MinerU|"
        r"\b(?:tool|platform|account|dashboard|plugin|workflow)\b",
        re.IGNORECASE,
    ),
    "parameter": re.compile(
        r"\u53c2\u6570|\u5b57\u6bb5|\u914d\u7f6e|\u9608\u503c|\u9650\u5236\u6761\u4ef6|"
        r"\b(?:threshold|retry_count|failure_reason|temperature|top_p|model|seed)\b|"
        r"\b[a-zA-Z_][\w-]*\s*=\s*[^,\s\uff0c\u3002]+",
        re.IGNORECASE,
    ),
    "link": re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE),
    "prompt": re.compile(r"\u63d0\u793a\u8bcd|prompt|\u6307\u4ee4", re.IGNORECASE),
    "code": re.compile(r"```|`[^`]+`|\b(?:def|class|const|let|function|import)\b", re.IGNORECASE),
    "table": re.compile(r"^\s*\|.+\|\s*$|<table\b", re.IGNORECASE | re.MULTILINE),
    "number_or_metric": re.compile(r"\d+(?:\.\d+)?\s*(?:%|GB|MB|KB|ms|s|\u5143|\u6b21|\u4e2a|\u5929)?"),
}

DETAIL_BLOCK_TYPES = {
    "operation_step": "operation_step",
    "tool_instruction": "tool_or_platform",
    "prompt": "prompt",
    "code": "code",
    "table": "table",
}

STRICT_DETAIL_CATEGORIES = {
    "operation_step",
    "tool_or_platform",
    "parameter",
    "link",
    "prompt",
    "code",
    "table",
}


def _image_retention_stats(image_blocks: list[dict], run_p: Path) -> dict:
    status_counts: dict[str, int] = {}
    referenced_files: list[str] = []
    missing_files: list[str] = []
    invalid_svg_files: list[str] = []
    for block in image_blocks:
        status = block.get("status", "unclassified")
        status_counts[status] = status_counts.get(status, 0) + 1
        if status == "discard":
            continue
        for src in _extract_image_sources(block.get("text", "")):
            if _is_external_image(src):
                continue
            referenced_files.append(src)
            resolved = _resolve_image_path(run_p, src)
            if not resolved.exists():
                missing_files.append(src)
            elif resolved.suffix.lower() == ".svg" and not _is_valid_standalone_svg(resolved):
                invalid_svg_files.append(src)

    return {
        "total_blocks": len(image_blocks),
        "keep_blocks": status_counts.get("keep", 0),
        "evidence_blocks": status_counts.get("evidence", 0),
        "review_blocks": status_counts.get("review", 0),
        "discard_blocks": status_counts.get("discard", 0),
        "referenced_file_count": len(referenced_files),
        "missing_file_count": len(missing_files),
        "missing_files": missing_files[:50],
        "invalid_svg_count": len(invalid_svg_files),
        "invalid_svg_files": invalid_svg_files[:50],
    }

def _is_external_image(src: str) -> bool:
    return bool(re.match(r"^(?:https?:)?//|^data:", src, re.IGNORECASE))

def _resolve_image_path(run_p: Path, src: str) -> Path:
    src = src.strip().strip("<>")
    path = Path(src)
    if path.is_absolute():
        return path
    return run_p / path

def _is_markdown_image_only(text: str) -> bool:
    return bool(re.fullmatch(r"!\[[^\]]*\]\([^)]+\)", text))

def _is_valid_standalone_svg(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return False
    match = re.search(r"<svg\b([^>]*)>", text, re.IGNORECASE | re.DOTALL)
    if not match:
        return False
    attrs = match.group(1)
    has_viewbox = bool(re.search(r"\bviewbox\s*=\s*(?:\"[^\"]+\"|'[^']+')", attrs, re.IGNORECASE))
    has_width = bool(re.search(r"\bwidth\s*=\s*(?:\"[^\"]+\"|'[^']+')", attrs, re.IGNORECASE))
    has_height = bool(re.search(r"\bheight\s*=\s*(?:\"[^\"]+\"|'[^']+')", attrs, re.IGNORECASE))
    return has_viewbox or (has_width and has_height)

def _detail_retention_stats(blocks: list[dict]) -> dict:
    stats = {
        category: {
            "total_blocks": 0,
            "kept_blocks": 0,
            "evidence_blocks": 0,
            "review_blocks": 0,
            "discarded_blocks": 0,
        }
        for category in DETAIL_SIGNAL_PATTERNS
    }
    discarded_detail_block_ids: list[str] = []

    for block in blocks:
        categories = _detail_categories(block)
        if not categories:
            continue

        status = block.get("status", "unclassified")
        status_key = {
            "keep": "kept_blocks",
            "evidence": "evidence_blocks",
            "review": "review_blocks",
            "discard": "discarded_blocks",
        }.get(status)

        for category in categories:
            stats[category]["total_blocks"] += 1
            if status_key:
                stats[category][status_key] += 1

        if status == "discard" and STRICT_DETAIL_CATEGORIES.intersection(categories):
            if "link" in categories and not (STRICT_DETAIL_CATEGORIES - {"link"}).intersection(categories):
                continue
            if not _is_known_pollution_without_detail(block, categories):
                discarded_detail_block_ids.append(str(block.get("block_id", "")))

    stats["discarded_detail_block_ids"] = [block_id for block_id in discarded_detail_block_ids if block_id]
    return stats

def _detail_categories(block: dict) -> set[str]:
    text = block.get("text", "")
    categories: set[str] = set()

    mapped_type = DETAIL_BLOCK_TYPES.get(block.get("type"))
    if mapped_type:
        categories.add(mapped_type)

    for category, pattern in DETAIL_SIGNAL_PATTERNS.items():
        if pattern.search(text):
            categories.add(category)

    return categories

def _is_known_pollution_without_detail(block: dict, categories: set[str]) -> bool:
    block_type = block.get("type")
    if block_type not in {
        "page_marker",
        "slide_chapter_divider",
        "translator_marketing_back_matter",
        "marketing_cta",
        "marketing_wrapper",
        "author_identity",
        "author_intro",
        "image_artifact",
        "layout_table_artifact",
        "layout_separator",
        "author_profile_links",
        "toc",
        "toc_heading",
        "empty_heading",
        "back_matter",
        "transcript_filler",
        "footer",
        "qr_image",
        "empty",
        "refund_policy",
    }:
        return False
    if block_type in {
        "page_marker",
        "slide_chapter_divider",
        "translator_marketing_back_matter",
        "author_identity",
        "author_intro",
        "author_profile_links",
        "image_artifact",
        "layout_table_artifact",
        "layout_separator",
        "toc",
        "toc_heading",
        "empty_heading",
    }:
        return True
    if block_type == "marketing_wrapper" and any(
        tag in block.get("risk_tags", [])
        for tag in [
            "drop_packaging_context_for_text_kb",
            "drop_packaging_heading_for_text_kb",
            "drop_brand_program_packaging_for_text_kb",
        ]
    ):
        return True
    if block_type == "marketing_cta" and "promotional_line" in block.get("risk_tags", []):
        return True
    return not STRICT_DETAIL_CATEGORIES.intersection(categories)

def _output_retention_stats(blocks: list[dict], run_p: Path) -> dict:
    cleaned_path = run_p / "cleaned.md"
    cleaned_text = cleaned_path.read_text(encoding="utf-8") if cleaned_path.exists() else ""
    primary_path = _primary_final_output_path(run_p, cleaned_path)
    primary_text = primary_path.read_text(encoding="utf-8") if primary_path.exists() else ""
    review_path = run_p / "review_needed.md"
    review_text = review_path.read_text(encoding="utf-8") if review_path.exists() else ""
    evidence_path = run_p / "evidence" / "marketing_pages.md"
    evidence_text = evidence_path.read_text(encoding="utf-8") if evidence_path.exists() else ""

    keep_blocks = [block for block in blocks if block.get("status") == "keep"]
    review_blocks = [block for block in blocks if block.get("status") == "review"]
    evidence_blocks = [block for block in blocks if block.get("status") == "evidence"]

    primary_stats = _destination_output_retention(keep_blocks, primary_text, primary_path.exists())
    cleaned_stats = _destination_output_retention(keep_blocks, cleaned_text, cleaned_path.exists())
    review_stats = _destination_output_retention(review_blocks, review_text, review_path.exists())
    evidence_stats = _destination_output_retention(evidence_blocks, evidence_text, evidence_path.exists())

    stats = {
        "checked_blocks": len(keep_blocks) + len(review_blocks) + len(evidence_blocks),
        "primary_output_path": str(primary_path),
        "cleaned_md_exists": cleaned_path.exists(),
        "review_needed_md_exists": review_path.exists(),
        "evidence_md_exists": evidence_path.exists(),
        "primary_output": {
            "path": str(primary_path),
            **primary_stats,
        },
        "cleaned_md": cleaned_stats,
        "review_needed_md": review_stats,
        "evidence_md": evidence_stats,
    }
    stats["missing_total"] = (
        primary_stats["missing_total"]
        + review_stats["missing_total"]
        + evidence_stats["missing_total"]
    )
    # Backward-compatible aliases for callers that only care about the primary final output.
    stats["link"] = primary_stats["link"]
    stats["parameter"] = primary_stats["parameter"]
    stats["code"] = primary_stats["code"]
    stats["table"] = primary_stats["table"]
    return stats

def _primary_final_output_path(run_p: Path, cleaned_path: Path) -> Path:
    obsidian_complete = run_p / "obsidian" / "01-完整正文.md"
    if obsidian_complete.exists():
        return obsidian_complete
    obsidian_dir = run_p / "obsidian"
    if obsidian_dir.exists():
        complete_candidates = [
            path for path in obsidian_dir.glob("*.md")
            if path.name != "00-索引.md"
        ]
        if len(complete_candidates) == 1:
            return complete_candidates[0]
    return cleaned_path

def _destination_output_retention(blocks: list[dict], target_text: str, target_exists: bool) -> dict:
    link = _signal_presence(
        _unique_signals(blocks, lambda text: DETAIL_SIGNAL_PATTERNS["link"].findall(text)),
        target_text,
        normalizer=_normalize_link_signal,
    )
    parameter = _signal_presence(
        _unique_signals(blocks, _extract_parameter_signals),
        target_text,
        normalizer=_normalize_parameter_signal,
    )
    code = _code_presence(blocks, target_text)
    table = _table_presence(blocks, target_text)
    missing_total = (
        len(link["missing"])
        + len(parameter["missing"])
        + code["missing_count"]
        + table["missing_count"]
    )
    return {
        "checked_blocks": len(blocks),
        "target_exists": target_exists,
        "missing_total": missing_total,
        "link": link,
        "parameter": parameter,
        "code": code,
        "table": table,
    }

def _unique_signals(blocks: list[dict], extractor) -> list[str]:
    seen: set[str] = set()
    signals: list[str] = []
    for block in blocks:
        text = block.get("text", "")
        for raw in extractor(text):
            signal = str(raw).strip().rstrip(".,;:!?，。；：！？")
            if not signal or signal in seen:
                continue
            seen.add(signal)
            signals.append(signal)
    return signals

def _extract_parameter_signals(text: str) -> list[str]:
    signals: list[str] = []
    for match in re.findall(r"\b(?:threshold|retry_count|failure_reason|temperature|top_p|model|seed)\s*=\s*[^,\s\uff0c\u3002]+", text, re.IGNORECASE):
        signals.append(match)
    return signals

def _signal_presence(signals: list[str], cleaned_text: str, normalizer=None) -> dict:
    if normalizer:
        normalized_text = normalizer(cleaned_text)
        missing = [signal for signal in signals if normalizer(signal) not in normalized_text]
    else:
        missing = [signal for signal in signals if signal not in cleaned_text]
    return {
        "total": len(signals),
        "present": len(signals) - len(missing),
        "missing_count": len(missing),
        "missing": missing[:50],
    }

def _code_presence(blocks: list[dict], cleaned_text: str) -> dict:
    code_blocks = [block.get("text", "") for block in blocks if block.get("type") == "code"]
    normalized_cleaned = _normalize_code_signal(cleaned_text)
    missing: list[str] = []
    for text in code_blocks:
        probe = _code_probe(text)
        if probe and _normalize_code_signal(probe) not in normalized_cleaned:
            missing.append(probe)
    return {
        "total": len(code_blocks),
        "present": len(code_blocks) - len(missing),
        "missing_count": len(missing),
        "missing": missing[:20],
    }

def _table_presence(blocks: list[dict], cleaned_text: str) -> dict:
    table_blocks = [block.get("text", "") for block in blocks if block.get("type") == "table"]
    target_rows = _table_rows(cleaned_text)
    missing: list[str] = []
    for text in table_blocks:
        probe = _table_probe(text)
        cells = _table_cells(probe) if probe else []
        if cells and not _table_cells_present(cells, target_rows):
            missing.append(probe)
    return {
        "total": len(table_blocks),
        "present": len(table_blocks) - len(missing),
        "missing_count": len(missing),
        "missing": missing[:20],
    }

def _code_probe(text: str) -> str:
    body = re.sub(r"^\s*```[^\n]*\n?", "", text.strip())
    body = re.sub(r"\n?```\s*$", "", body)
    for line in body.splitlines():
        line = line.strip()
        if line:
            return line
    return ""

def _table_probe(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line and not re.fullmatch(r"\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?", line):
            return line
    return ""

def _normalize_parameter_signal(text: str) -> str:
    return re.sub(r"\s+", "", text).casefold()

def _normalize_link_signal(text: str) -> str:
    return text.casefold()

def _normalize_code_signal(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())

def _table_rows(text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or "|" not in stripped:
            continue
        if re.fullmatch(r"\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?", stripped):
            continue
        cells = _table_cells(stripped)
        if cells:
            rows.append(cells)
    return rows

def _table_cells(line: str) -> list[str]:
    return [
        re.sub(r"\s+", " ", cell.strip()).casefold()
        for cell in line.strip().strip("|").split("|")
        if cell.strip()
    ]

def _table_cells_present(cells: list[str], target_rows: list[list[str]]) -> bool:
    expected = set(cells)
    return any(expected.issubset(set(row)) for row in target_rows)
