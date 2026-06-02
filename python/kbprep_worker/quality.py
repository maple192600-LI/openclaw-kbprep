"""
quality - quality gate.
Checks: conversion quality, cleaning quality, splitting quality.
Outputs: quality_report.json with strict errors and warnings.
"""
import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Thresholds ────────────────────────────────────────────────────

CONVERSION_THRESHOLDS = {
    "garbage_ratio_warn": 0.03,
    "garbage_ratio_strict": 0.08,
    "empty_page_ratio_warn": 0.05,
    "missing_image_file_strict": 1,
}

CLEANING_THRESHOLDS = {
    "protected_block_loss_strict": 0,
    "operation_step_loss_strict": 0,
    "prompt_loss_strict": 0,
    "code_block_loss_strict": 0,
    "table_loss_strict": 0,
    "qr_image_in_cleaned_strict": 0,
    "cta_in_cleaned_strict": 0,
    "discard_ratio_warn": 0.25,
    "discard_ratio_strict": 0.45,
}

SPLITTING_THRESHOLDS = {
    "chunk_chars_min_warn": 300,
    "chunk_chars_max_warn": 3500,
    "broken_ordered_list_strict": 0,
    "broken_code_block_strict": 0,
    "broken_table_strict": 0,
    "missing_block_trace_strict": 0,
}

COVERAGE_THRESHOLDS = {
    "warn": {
        "pdf_like": 0.82,
        "markdown_note": 0.86,
        "generic_block": 0.88,
    },
    "strict": {
        "pdf_like": 0.72,
        "markdown_note": 0.76,
        "generic_block": 0.78,
    },
}


def run_quality_check(
    blocks: list[dict],
    run_dir: str,
    source_type: str,
    diagnosis: dict,
) -> dict:
    """
    Run all quality checks and produce quality_report.json.
    """
    strict_errors = []
    warnings = []
    run_p = Path(run_dir)

    # ── Conversion quality ────────────────────────────────────────
    conversion_report = _read_json_file(run_p / "conversion_report.json")
    source_text_layer = _source_text_layer_status(diagnosis, conversion_report)
    text_quality = diagnosis.get("text_quality", {})
    garbled_ratio = text_quality.get("garbled_ratio", 0)
    unreadable_ratio = text_quality.get("unreadable_text_ratio", 0)
    mojibake_ratio = text_quality.get("mojibake_ratio", 0)
    if source_text_layer["superseded_by_conversion"]:
        if max(garbled_ratio, unreadable_ratio, mojibake_ratio) > CONVERSION_THRESHOLDS["garbage_ratio_warn"]:
            warnings.append(
                "W_SOURCE_TEXT_LAYER_SUPERSEDED: source PDF text layer is unreadable, "
                "so final quality is judged from the converted/OCR output."
            )
    else:
        if garbled_ratio > CONVERSION_THRESHOLDS["garbage_ratio_strict"]:
            strict_errors.append(f"E_TEXT_LAYER_GARBLED: garbled ratio {garbled_ratio:.2%} exceeds strict threshold")
        elif garbled_ratio > CONVERSION_THRESHOLDS["garbage_ratio_warn"]:
            warnings.append(f"W_PDF_TEXT_LAYER_UNTRUSTED: garbled ratio {garbled_ratio:.2%}")
        if unreadable_ratio > CONVERSION_THRESHOLDS["garbage_ratio_strict"]:
            strict_errors.append(f"E_TEXT_LAYER_UNREADABLE: unreadable ratio {unreadable_ratio:.2%} exceeds strict threshold")
        elif unreadable_ratio > CONVERSION_THRESHOLDS["garbage_ratio_warn"]:
            warnings.append(f"W_PDF_TEXT_LAYER_UNTRUSTED: unreadable ratio {unreadable_ratio:.2%}")
        if mojibake_ratio > CONVERSION_THRESHOLDS["garbage_ratio_strict"]:
            strict_errors.append(f"E_TEXT_LAYER_MOJIBAKE: mojibake ratio {mojibake_ratio:.2%} exceeds strict threshold")
        elif mojibake_ratio > CONVERSION_THRESHOLDS["garbage_ratio_warn"]:
            warnings.append(f"W_PDF_TEXT_LAYER_UNTRUSTED: mojibake ratio {mojibake_ratio:.2%}")

    converted_text_quality = _converted_text_quality(conversion_report)
    if converted_text_quality:
        converted_garbled = converted_text_quality.get("garbled_ratio", 0)
        converted_unreadable = converted_text_quality.get("unreadable_text_ratio", 0)
        converted_mojibake = converted_text_quality.get("mojibake_ratio", 0)
        if converted_garbled > CONVERSION_THRESHOLDS["garbage_ratio_strict"]:
            strict_errors.append(f"E_CONVERTED_TEXT_GARBLED: converted text garbled ratio {converted_garbled:.2%} exceeds strict threshold")
        if converted_unreadable > CONVERSION_THRESHOLDS["garbage_ratio_strict"]:
            strict_errors.append(f"E_CONVERTED_TEXT_UNREADABLE: converted text unreadable ratio {converted_unreadable:.2%} exceeds strict threshold")
        if converted_mojibake > CONVERSION_THRESHOLDS["garbage_ratio_strict"]:
            strict_errors.append(f"E_CONVERTED_TEXT_MOJIBAKE: converted text mojibake ratio {converted_mojibake:.2%} exceeds strict threshold")

    # ── Cleaning quality ──────────────────────────────────────────
    total_blocks = len(blocks)
    status_counts = {}
    for b in blocks:
        s = b.get("status", "unclassified")
        status_counts[s] = status_counts.get(s, 0) + 1

    keep_count = status_counts.get("keep", 0)
    discard_count = status_counts.get("discard", 0)
    evidence_count = status_counts.get("evidence", 0)
    review_count = status_counts.get("review", 0)
    operation_step_blocks = [b for b in blocks if b.get("type") == "operation_step"]
    prompt_blocks = [b for b in blocks if b.get("type") == "prompt"]
    code_blocks = [b for b in blocks if b.get("type") == "code"]
    table_blocks = [b for b in blocks if b.get("type") == "table"]
    image_blocks = [b for b in blocks if _is_image_block(b)]

    # Check protected block loss
    protected_blocks = [b for b in blocks if b.get("protected")]
    protected_discarded = [b for b in protected_blocks if b.get("status") == "discard"]
    if len(protected_discarded) > CLEANING_THRESHOLDS["protected_block_loss_strict"]:
        strict_errors.append(f"E_QA_FAILED: {len(protected_discarded)} protected blocks were discarded")

    # Check operation_step loss
    op_step_blocks = operation_step_blocks
    op_step_discarded = [b for b in op_step_blocks if b.get("status") == "discard"]
    if len(op_step_discarded) > CLEANING_THRESHOLDS["operation_step_loss_strict"]:
        strict_errors.append(f"E_QA_FAILED: {len(op_step_discarded)} operation_step blocks were discarded")

    # Check code/table loss
    code_discarded = [b for b in code_blocks if b.get("status") == "discard"]
    if len(code_discarded) > CLEANING_THRESHOLDS["code_block_loss_strict"]:
        strict_errors.append(f"E_QA_FAILED: {len(code_discarded)} code blocks were discarded")

    table_discarded = [b for b in table_blocks if b.get("status") == "discard"]
    if len(table_discarded) > CLEANING_THRESHOLDS["table_loss_strict"]:
        strict_errors.append(f"E_QA_FAILED: {len(table_discarded)} table blocks were discarded")

    # Check CTA in cleaned.md
    cleaned_path = run_p / "cleaned.md"
    if cleaned_path.exists():
        cleaned_text = cleaned_path.read_text(encoding="utf-8")
        cta_re = re.compile(
            r'扫码(?:加入|入群|进群|加群)|二维码|长按识别|添加(?:微信|好友|客服|服务官)|微信号|免费领取.*体验卡|领取福利|立即购买|限时优惠',
            re.IGNORECASE,
        )
        cta_violations = [
            b for b in blocks
            if b.get("status") == "keep"
            and cta_re.search(b.get("text", ""))
            and not _allows_cta_keyword_context(b)
        ]
        if len(cta_violations) > CLEANING_THRESHOLDS["cta_in_cleaned_strict"]:
            strict_errors.append(f"E_QA_FAILED: {len(cta_violations)} CTA patterns found in non-protected cleaned blocks")

        # Check QR images in cleaned.md
        qr_re = re.compile(r'!\[.*\]\(.*(?:qr|二维码|QR).*\)', re.IGNORECASE)
        qr_matches = qr_re.findall(cleaned_text)
        if len(qr_matches) > CLEANING_THRESHOLDS["qr_image_in_cleaned_strict"]:
            strict_errors.append(f"E_QA_FAILED: {len(qr_matches)} QR images found in cleaned.md")

    # Check discard ratio against body candidates, not obvious pollution.
    discard_ratio_blocks = [b for b in blocks if _counts_for_discard_ratio(b)]
    discard_ratio_discarded = [b for b in discard_ratio_blocks if b.get("status") == "discard"]
    discard_ratio = 0.0
    if discard_ratio_blocks:
        discard_ratio = len(discard_ratio_discarded) / len(discard_ratio_blocks)
        if discard_ratio > CLEANING_THRESHOLDS["discard_ratio_strict"]:
            strict_errors.append(f"E_QA_FAILED: discard ratio {discard_ratio:.2%} exceeds strict threshold")
        elif discard_ratio > CLEANING_THRESHOLDS["discard_ratio_warn"]:
            warnings.append(f"W_LOW_COVERAGE: discard ratio {discard_ratio:.2%}")

    # ── Splitting quality ─────────────────────────────────────────
    chunks_dir = run_p / "chunks"
    chunk_chars = []
    if chunks_dir.exists():
        for chunk_file in sorted(chunks_dir.glob("*.md")):
            text = chunk_file.read_text(encoding="utf-8")
            # Strip frontmatter
            if text.startswith("---"):
                end = text.find("---", 3)
                if end > 0:
                    text = text[end + 3:].strip()
            chunk_chars.append(len(text))

    if chunk_chars:
        too_short = sum(1 for c in chunk_chars if c < SPLITTING_THRESHOLDS["chunk_chars_min_warn"])
        too_long = sum(1 for c in chunk_chars if c > SPLITTING_THRESHOLDS["chunk_chars_max_warn"])

        if too_short > 0:
            warnings.append(f"W_LOW_COVERAGE: {too_short} chunks below {SPLITTING_THRESHOLDS['chunk_chars_min_warn']} chars")
        if too_long > 0:
            warnings.append(f"W_LOW_COVERAGE: {too_long} chunks above {SPLITTING_THRESHOLDS['chunk_chars_max_warn']} chars")

    # Check for broken code blocks in chunks
    # (simplified: check if any chunk starts with ``` but doesn't end with ```)
    broken_code = 0
    if chunks_dir.exists():
        for chunk_file in sorted(chunks_dir.glob("*.md")):
            text = chunk_file.read_text(encoding="utf-8")
            code_fences = text.count("```")
            if code_fences % 2 != 0:
                broken_code += 1
    if broken_code > SPLITTING_THRESHOLDS["broken_code_block_strict"]:
        strict_errors.append(f"E_QA_FAILED: {broken_code} chunks have broken code blocks")

    # ── Coverage ratio ────────────────────────────────────────────
    coverage = 1.0
    coverage_blocks = [b for b in blocks if _counts_for_text_coverage(b)]
    excluded_coverage_blocks = [b for b in blocks if not _counts_for_text_coverage(b)]
    if coverage_blocks:
        keep_chars = sum(len(b.get("text", "")) for b in coverage_blocks if b.get("status") == "keep")
        total_chars = sum(len(b.get("text", "")) for b in coverage_blocks)
        coverage = keep_chars / total_chars if total_chars > 0 else 1.0
    excluded_coverage_chars = sum(len(b.get("text", "")) for b in excluded_coverage_blocks)

    coverage_warn = COVERAGE_THRESHOLDS["warn"].get(source_type, 0.80)
    coverage_strict = COVERAGE_THRESHOLDS["strict"].get(source_type, 0.70)

    if coverage < coverage_strict:
        strict_errors.append(f"E_QA_FAILED: coverage {coverage:.2%} below strict threshold {coverage_strict:.0%}")
    elif coverage < coverage_warn:
        warnings.append(f"W_LOW_COVERAGE: coverage {coverage:.2%} below warn threshold {coverage_warn:.0%}")

    image_stats = _image_retention_stats(image_blocks, run_p)
    if image_stats["missing_file_count"] >= CONVERSION_THRESHOLDS["missing_image_file_strict"]:
        strict_errors.append(f"E_QA_FAILED: {image_stats['missing_file_count']} referenced image files are missing")
    if image_stats.get("invalid_svg_count", 0) > 0:
        strict_errors.append(f"E_QA_FAILED: {image_stats['invalid_svg_count']} SVG diagram files have invalid root dimensions")

    detail_stats = _detail_retention_stats(blocks)
    if detail_stats["discarded_detail_block_ids"]:
        strict_errors.append(
            "E_QA_FAILED: "
            f"{len(detail_stats['discarded_detail_block_ids'])} detail-bearing blocks were discarded"
        )

    output_stats = _output_retention_stats(blocks, run_p)
    if output_stats["missing_total"] > 0:
        strict_errors.append(
            "E_QA_FAILED: "
            f"{output_stats['missing_total']} kept detail signals missing from final knowledge output"
        )

    # ── Build report ──────────────────────────────────────────────
    report = {
        "source_sha256": diagnosis.get("file_id", ""),
        "source_type": source_type,
        "total_blocks": total_blocks,
        "keep_blocks": keep_count,
        "discard_blocks": discard_count,
        "evidence_blocks": evidence_count,
        "review_blocks": review_count,
        "discard_ratio": round(discard_ratio, 4),
        "discard_ratio_scope": "body_candidate_blocks_excluding_known_pollution",
        "discard_ratio_evaluated_blocks": len(discard_ratio_blocks),
        "discard_ratio_excluded_blocks": total_blocks - len(discard_ratio_blocks),
        "coverage_ratio": round(coverage, 4),
        "coverage_scope": "text_blocks_excluding_image_only_evidence",
        "coverage_evaluated_blocks": len(coverage_blocks),
        "coverage_excluded_blocks": len(excluded_coverage_blocks),
        "coverage_excluded_chars": excluded_coverage_chars,
        "retention": {
            "operation_step_total": len(operation_step_blocks),
            "operation_step_discarded": len(op_step_discarded),
            "prompt_total": len(prompt_blocks),
            "prompt_discarded": len([b for b in prompt_blocks if b.get("status") == "discard"]),
            "code_total": len(code_blocks),
            "code_discarded": len(code_discarded),
            "table_total": len(table_blocks),
            "table_discarded": len(table_discarded),
            "image_total": image_stats["total_blocks"],
            "image_keep": image_stats["keep_blocks"],
            "image_evidence": image_stats["evidence_blocks"],
            "image_review": image_stats["review_blocks"],
            "image_discarded": image_stats["discard_blocks"],
            "image_referenced_files": image_stats["referenced_file_count"],
            "image_missing_files": image_stats["missing_file_count"],
            "image_invalid_svg_files": image_stats.get("invalid_svg_count", 0),
        },
        "detail_retention": detail_stats,
        "source_text_layer": source_text_layer,
        "output_retention": output_stats,
        "image_retention": image_stats,
        "chunk_count": len(chunk_chars),
        "chunk_chars_avg": round(sum(chunk_chars) / len(chunk_chars)) if chunk_chars else 0,
        "strict_errors": strict_errors,
        "warnings": warnings,
        "thresholds": {
            "conversion": CONVERSION_THRESHOLDS,
            "cleaning": CLEANING_THRESHOLDS,
            "splitting": SPLITTING_THRESHOLDS,
            "coverage": COVERAGE_THRESHOLDS,
        },
    }

    return report


def _read_json_file(path: Path) -> dict:
    try:
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _source_text_layer_status(diagnosis: dict, conversion_report: dict) -> dict:
    text_quality = diagnosis.get("text_quality", {})
    converter = str(conversion_report.get("converter") or "")
    superseded = _conversion_supersedes_source_text_layer(diagnosis, conversion_report)
    return {
        "text_layer_health": diagnosis.get("text_layer_health"),
        "pdf_subtype": diagnosis.get("pdf_subtype"),
        "needs_ocr": bool(diagnosis.get("needs_ocr")),
        "converter": converter,
        "superseded_by_conversion": superseded,
        "garbled_ratio": text_quality.get("garbled_ratio", 0),
        "unreadable_text_ratio": text_quality.get("unreadable_text_ratio", 0),
        "mojibake_ratio": text_quality.get("mojibake_ratio", 0),
    }


def _conversion_supersedes_source_text_layer(diagnosis: dict, conversion_report: dict) -> bool:
    converter = str(conversion_report.get("converter") or "")
    converted_bytes = int(conversion_report.get("converted_bytes") or 0)
    if converter not in {"mineru", "mineru_after_pdf_text_layer_fallback"}:
        return False
    if converted_bytes <= 0:
        return False
    return bool(
        diagnosis.get("needs_ocr")
        or diagnosis.get("pdf_subtype") == "garbled_text_layer"
        or diagnosis.get("text_layer_health") in {"bad", "untrusted"}
    )


def _converted_text_quality(conversion_report: dict) -> dict:
    artifacts = conversion_report.get("mineru_artifacts")
    if not isinstance(artifacts, dict):
        return {}
    quality = artifacts.get("post_convert_text_quality")
    return quality if isinstance(quality, dict) else {}


def _allows_cta_keyword_context(block: dict) -> bool:
    """CTA words can be legitimate when a protected tutorial block discusses rules or bad examples."""
    if block.get("protected"):
        return True
    if block.get("type") in {"operation_step", "case_step", "tool_instruction", "prompt", "code", "table"}:
        return True
    text = block.get("text", "")
    return any(term in text for term in ["平台规则", "违规案例", "不要", "判断标准", "限制条件"])


DISCARDED_BODY_LOSS_EXEMPT_TYPES = {
    "transcript_filler",
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
    "refund_policy",
    "footer",
    "qr_image",
    "empty",
}


def _counts_for_text_coverage(block: dict) -> bool:
    """Coverage gates measure body text retention, not image-link bookkeeping."""
    block_type = block.get("type")
    text = block.get("text", "").strip()
    if block.get("status") == "discard" and block_type in DISCARDED_BODY_LOSS_EXEMPT_TYPES:
        return False
    if block_type in {"image_evidence", "image_operation", "diagram"}:
        return not _is_markdown_image_only(text)
    return True


def _counts_for_discard_ratio(block: dict) -> bool:
    """Discard ratio gates body loss, not successful removal of known pollution."""
    block_type = block.get("type")
    if block.get("status") == "discard" and block_type in DISCARDED_BODY_LOSS_EXEMPT_TYPES:
        return False
    return _counts_for_text_coverage(block)


def _is_image_block(block: dict) -> bool:
    return block.get("type") in {"image_evidence", "image_operation", "diagram", "qr_image", "unknown_image"}


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


def _extract_image_sources(text: str) -> list[str]:
    return [match.strip() for match in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text or "") if match.strip()]


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
    if re.search(r"\bviewbox\s*=", attrs):
        return False
    if not re.search(r'\bviewBox\s*=\s*"[^"]+"', attrs):
        return False
    if not re.search(r'\bwidth\s*=\s*"[^"]+"', attrs):
        return False
    if not re.search(r'\bheight\s*=\s*"[^"]+"', attrs):
        return False
    return True


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
        r"\u63d2\u4ef6|APP|API|GitHub|YouTube|OpenClaw|Obsidian|MinerU|"
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
    return cleaned_path


def _destination_output_retention(blocks: list[dict], target_text: str, target_exists: bool) -> dict:
    link = _signal_presence(
        _unique_signals(blocks, lambda text: DETAIL_SIGNAL_PATTERNS["link"].findall(text)),
        target_text,
    )
    parameter = _signal_presence(
        _unique_signals(blocks, _extract_parameter_signals),
        target_text,
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


def _signal_presence(signals: list[str], cleaned_text: str) -> dict:
    missing = [signal for signal in signals if signal not in cleaned_text]
    return {
        "total": len(signals),
        "present": len(signals) - len(missing),
        "missing_count": len(missing),
        "missing": missing[:50],
    }


def _code_presence(blocks: list[dict], cleaned_text: str) -> dict:
    code_blocks = [block.get("text", "") for block in blocks if block.get("type") == "code"]
    missing: list[str] = []
    for text in code_blocks:
        probe = _code_probe(text)
        if probe and probe not in cleaned_text:
            missing.append(probe)
    return {
        "total": len(code_blocks),
        "present": len(code_blocks) - len(missing),
        "missing_count": len(missing),
        "missing": missing[:20],
    }


def _table_presence(blocks: list[dict], cleaned_text: str) -> dict:
    table_blocks = [block.get("text", "") for block in blocks if block.get("type") == "table"]
    missing: list[str] = []
    for text in table_blocks:
        probe = _table_probe(text)
        if probe and probe not in cleaned_text:
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
