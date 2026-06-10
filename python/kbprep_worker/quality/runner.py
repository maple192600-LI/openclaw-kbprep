"""Quality gate runner."""

import json
import logging
from pathlib import Path

from ..rule_loader import load_cleaning_rules
from .cleanup_safety import (
    _allows_cta_keyword_context,
    _counts_for_discard_ratio,
    _counts_for_text_coverage,
    _is_image_block,
    _matches_cleanup_pollution,
    _qr_image_matches,
)
from .conversion_integrity import (
    _converted_text_quality,
    _conversion_structure_integrity,
    _source_conversion_integrity,
    _source_text_layer_status,
)
from .gates import (
    _build_quality_gates,
    _quality_tasks_from_actions,
    _write_quality_gate_artifacts,
)
from .io import _read_json_file
from .markdown_signals import _detect_language_from_blocks
from .retention import _detail_retention_stats, _image_retention_stats, _output_retention_stats
from .thresholds import (
    CLEANING_THRESHOLDS,
    CONVERSION_THRESHOLDS,
    COVERAGE_THRESHOLDS,
    SPLITTING_THRESHOLDS,
)

logger = logging.getLogger(__name__)

def run_quality_check(
    blocks: list[dict],
    run_dir: str,
    source_type: str,
    diagnosis: dict,
    profile: str = "standard",
    document_type: str = "",
    rule_templates: list[str] | tuple[str, ...] | None = None,
    review_applied_at: float | int | None = None,
    quality_iteration: int | str | None = 1,
    max_quality_iterations: int | str | None = 3,
    previous_quality_iteration: int | str | None = None,
) -> dict:
    """
    Run all quality checks and produce quality_report.json.
    """
    strict_errors = []
    warnings = []
    run_p = Path(run_dir)
    cleaning_rules = load_cleaning_rules(
        profile=profile,
        document_type=document_type,
        templates=tuple(rule_templates or ()),
    )

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

    source_conversion_integrity = _source_conversion_integrity(run_p, conversion_report)
    (run_p / "source_conversion_integrity.json").write_text(
        json.dumps(source_conversion_integrity, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    if source_conversion_integrity.get("missing_heading_count", 0) > CONVERSION_THRESHOLDS["structure_loss_strict"]:
        strict_errors.append(
            "E_SOURCE_CONVERSION_LOSS: "
            f"{source_conversion_integrity['missing_heading_count']} source headings missing from converted Markdown"
        )
    if source_conversion_integrity.get("missing_table_count", 0) > CONVERSION_THRESHOLDS["structure_loss_strict"]:
        strict_errors.append(
            "E_SOURCE_CONVERSION_LOSS: "
            f"{source_conversion_integrity['missing_table_count']} source tables missing from converted Markdown"
        )
    if source_conversion_integrity.get("missing_code_block_count", 0) > CONVERSION_THRESHOLDS["structure_loss_strict"]:
        strict_errors.append(
            "E_SOURCE_CONVERSION_LOSS: "
            f"{source_conversion_integrity['missing_code_block_count']} source code blocks missing from converted Markdown"
        )
    if source_conversion_integrity.get("missing_image_ref_count", 0) > CONVERSION_THRESHOLDS["structure_loss_strict"]:
        strict_errors.append(
            "E_SOURCE_CONVERSION_LOSS: "
            f"{source_conversion_integrity['missing_image_ref_count']} source image references missing from converted Markdown"
        )

    structure_integrity = _conversion_structure_integrity(blocks, run_p)
    if structure_integrity["missing_heading_count"] > CONVERSION_THRESHOLDS["structure_loss_strict"]:
        strict_errors.append(
            "E_CONVERSION_STRUCTURE_LOSS: "
            f"{structure_integrity['missing_heading_count']} converted headings missing from block trace"
        )
    if structure_integrity["missing_table_count"] > CONVERSION_THRESHOLDS["structure_loss_strict"]:
        strict_errors.append(
            "E_CONVERSION_STRUCTURE_LOSS: "
            f"{structure_integrity['missing_table_count']} converted tables missing from block trace"
        )
    if structure_integrity["missing_code_block_count"] > CONVERSION_THRESHOLDS["structure_loss_strict"]:
        strict_errors.append(
            "E_CONVERSION_STRUCTURE_LOSS: "
            f"{structure_integrity['missing_code_block_count']} converted code blocks missing from block trace"
        )
    if structure_integrity["missing_image_ref_count"] > CONVERSION_THRESHOLDS["structure_loss_strict"]:
        strict_errors.append(
            "E_CONVERSION_STRUCTURE_LOSS: "
            f"{structure_integrity['missing_image_ref_count']} converted image references missing from block trace"
        )

    # ── Cleaning quality ──────────────────────────────────────────
    total_blocks = len(blocks)
    status_counts: dict[str, int] = {}
    for b in blocks:
        s = str(b.get("status", "unclassified"))
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
        cta_violations = [
            b for b in blocks
            if b.get("status") == "keep"
            and _matches_cleanup_pollution(b.get("text", ""), cleaning_rules)
            and not _allows_cta_keyword_context(b, cleaning_rules)
        ]
        if len(cta_violations) > CLEANING_THRESHOLDS["cta_in_cleaned_strict"]:
            strict_errors.append(f"E_QA_FAILED: {len(cta_violations)} CTA patterns found in non-protected cleaned blocks")

        # Check QR images in cleaned.md
        qr_matches = _qr_image_matches(cleaned_text, cleaning_rules)
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

    quality_loop = _quality_loop_state(
        strict_errors=strict_errors,
        quality_iteration=quality_iteration,
        max_quality_iterations=max_quality_iterations,
        previous_quality_iteration=previous_quality_iteration,
    )
    if quality_loop["status"] == "iteration_limit_reached":
        strict_errors.append(
            "E_QUALITY_ITERATION_LIMIT: "
            f"quality loop reached iteration {quality_loop['current_iteration']} "
            f"of {quality_loop['max_iterations']} while strict errors remain"
        )
        quality_loop["strict_error_count"] = len(strict_errors)

    # ── Build report ──────────────────────────────────────────────
    report = {
        "source_sha256": diagnosis.get("file_id", ""),
        "source_type": source_type,
        "profile": profile,
        "document_type": document_type,
        "rule_templates": list(rule_templates or []),
        "language_detected": _detect_language_from_blocks(blocks),
        "cleaning_rule_sources": list(cleaning_rules.sources),
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
        "source_conversion_integrity": source_conversion_integrity,
        "conversion_structure_integrity": structure_integrity,
        "output_retention": output_stats,
        "image_retention": image_stats,
        "quality_loop": quality_loop,
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
    if review_applied_at is not None:
        report["review_applied_at"] = review_applied_at
    gates, next_actions = _build_quality_gates(strict_errors, warnings, report)
    if quality_loop["status"] == "iteration_limit_reached":
        next_actions = [
            {
                "gate": "export_readiness",
                "action": "stop_iteration",
                "target": "quality_loop",
                "reason": "Quality still fails after the configured maximum review/cleanup iterations.",
                "strict_error_count": len(strict_errors),
            },
            *next_actions,
        ]
    report["quality_gates"] = gates
    report["next_actions"] = next_actions
    report["quality_tasks"] = _quality_tasks_from_actions(report, next_actions, run_p)
    report["quality_gate_artifacts"] = _write_quality_gate_artifacts(report, gates, run_p)

    return report

def _quality_loop_state(
    strict_errors: list[str],
    quality_iteration: int | str | None,
    max_quality_iterations: int | str | None,
    previous_quality_iteration: int | str | None,
) -> dict:
    current = _positive_int(quality_iteration, 1)
    max_iterations = _positive_int(max_quality_iterations, 3)
    previous = _non_negative_int(previous_quality_iteration, current - 1 if current > 1 else 0)
    has_strict_errors = bool(strict_errors)
    limit_reached = has_strict_errors and current >= max_iterations
    if not has_strict_errors:
        status = "passed"
    elif limit_reached:
        status = "iteration_limit_reached"
    else:
        status = "needs_iteration"
    return {
        "current_iteration": current,
        "previous_iteration": previous,
        "max_iterations": max_iterations,
        "remaining_iterations": max(0, max_iterations - current),
        "can_continue": has_strict_errors and not limit_reached,
        "status": status,
        "strict_error_count": len(strict_errors),
    }

def _positive_int(value: int | str | None, default: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError):
        parsed = default
    return max(1, parsed)

def _non_negative_int(value: int | str | None, default: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError):
        parsed = default
    return max(0, parsed)
