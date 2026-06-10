"""Deterministic repair-loop helpers for failed prepare runs."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any


def build_failure_diagnosis(*, state: Any) -> dict[str, Any]:
    quality = state.quality_report or {}
    strict_errors = list(state.strict_errors)
    image_retention = quality.get("image_retention") or {}
    detail_retention = quality.get("detail_retention") or {}
    source_integrity = quality.get("source_conversion_integrity") or {}
    structure_integrity = quality.get("conversion_structure_integrity") or {}
    output_retention = quality.get("output_retention") or {}

    failure_types: list[str] = []
    if image_retention.get("missing_file_count", 0) > 0:
        failure_types.append("missing_assets")
    if detail_retention.get("discarded_detail_block_ids"):
        failure_types.append("discarded_detail")
    if source_integrity.get("missing_heading_count", 0) or source_integrity.get("missing_table_count", 0) or source_integrity.get("missing_code_block_count", 0):
        failure_types.append("conversion_loss")
    if structure_integrity.get("missing_heading_count", 0) or structure_integrity.get("missing_table_count", 0) or structure_integrity.get("missing_code_block_count", 0):
        failure_types.append("block_trace_loss")
    if output_retention.get("missing_total", 0) > 0:
        failure_types.append("output_detail_loss")
    if any("CTA patterns found" in error or "QR images found" in error for error in strict_errors):
        failure_types.append("pollution_residue")
    if not failure_types:
        failure_types.append("unknown_quality_failure")

    return {
        "schema": "kbprep.failure_diagnosis.v1",
        "run_id": state.run_id,
        "run_dir": str(state.run_dir),
        "input_path": str(state.input_p),
        "output_root": str(state.root_p),
        "repair_iteration": state.repair_iteration,
        "max_quality_iterations": state.max_quality_iterations,
        "failure_types": sorted(set(failure_types)),
        "strict_errors": strict_errors,
        "quality_gates": quality.get("quality_gates", []),
        "next_actions": quality.get("next_actions", []),
        "evidence": {
            "missing_assets": image_retention.get("missing_files", []),
            "discarded_detail_block_ids": detail_retention.get("discarded_detail_block_ids", []),
            "source_conversion_integrity": source_integrity,
            "conversion_structure_integrity": structure_integrity,
            "output_retention": output_retention,
        },
    }


def build_repair_actions(*, state: Any, diagnosis: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    missing_assets = diagnosis.get("evidence", {}).get("missing_assets", [])
    if missing_assets:
        actions.append({
            "id": "copy-discoverable-markdown-assets",
            "type": "copy_missing_assets",
            "status": "pending",
            "safe_to_apply": True,
            "missing_assets": missing_assets,
            "description": "Copy local Markdown image assets from sibling assets folders into the run directory, then rerun quality checks.",
        })

    discarded_ids = diagnosis.get("evidence", {}).get("discarded_detail_block_ids", [])
    if discarded_ids:
        actions.append({
            "id": "restore-discarded-detail-blocks",
            "type": "restore_detail_blocks",
            "status": "pending",
            "safe_to_apply": True,
            "block_ids": discarded_ids,
            "description": "Move detail-bearing blocks that were discarded by cleanup back to keep before publication.",
        })

    if "pollution_residue" in diagnosis.get("failure_types", []):
        actions.append({
            "id": "propose-pollution-cleanup-rule",
            "type": "manual_rule_proposal",
            "status": "manual_required",
            "safe_to_apply": False,
            "description": "Create or accept a cleanup rule proposal before rerunning; accepted rules are never promoted automatically.",
        })

    if "conversion_loss" in diagnosis.get("failure_types", []) or "block_trace_loss" in diagnosis.get("failure_types", []):
        actions.append({
            "id": "inspect-conversion-loss",
            "type": "manual_conversion_review",
            "status": "manual_required",
            "safe_to_apply": False,
            "description": "Inspect converted.md and source evidence; KBPrep must not publish final Markdown while source structure is missing.",
        })

    if not actions:
        actions.append({
            "id": "manual-quality-review",
            "type": "manual_quality_review",
            "status": "manual_required",
            "safe_to_apply": False,
            "description": "Inspect quality_report.json, discarded.md, and review_needed.md before rerunning.",
        })

    return actions


def write_repair_artifacts(*, state: Any, diagnosis: dict[str, Any], actions: list[dict[str, Any]]) -> dict[str, str]:
    run_dir = Path(state.run_dir)
    diagnosis_path = run_dir / "failure_diagnosis.json"
    actions_path = run_dir / "repair_actions.json"
    plan_path = run_dir / "repair_plan.md"

    diagnosis_path.write_text(json.dumps(diagnosis, indent=2, ensure_ascii=False), encoding="utf-8")
    actions_path.write_text(json.dumps({
        "schema": "kbprep.repair_actions.v1",
        "run_id": state.run_id,
        "actions": actions,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    plan_path.write_text(_render_repair_plan(diagnosis, actions), encoding="utf-8")

    return {
        "failure_diagnosis": str(diagnosis_path),
        "repair_actions": str(actions_path),
        "repair_plan": str(plan_path),
    }


def apply_safe_repairs(*, state: Any, actions: list[dict[str, Any]]) -> dict[str, Any]:
    applied: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for action in actions:
        if not action.get("safe_to_apply"):
            skipped.append({**action, "status": "manual_required"})
            continue
        if action.get("type") == "copy_missing_assets":
            result = _copy_missing_assets(state, action.get("missing_assets") or [])
            if result["copied_count"]:
                applied.append({**action, "status": "applied", "result": result})
            else:
                skipped.append({**action, "status": "not_applied", "result": result})
            continue
        if action.get("type") == "restore_detail_blocks":
            result = _restore_detail_blocks(state, action.get("block_ids") or [])
            if result["restored_count"]:
                applied.append({**action, "status": "applied", "result": result})
            else:
                skipped.append({**action, "status": "not_applied", "result": result})
            continue
        skipped.append({**action, "status": "unsupported"})

    return {
        "schema": "kbprep.repair_result.v1",
        "applied": applied,
        "skipped": skipped,
        "applied_count": len(applied),
    }


def _copy_missing_assets(state: Any, missing_assets: list[str]) -> dict[str, Any]:
    copied: list[dict[str, str]] = []
    unresolved: list[str] = []
    for asset in missing_assets:
        relative_asset = _safe_relative_asset(asset)
        if not relative_asset:
            unresolved.append(str(asset))
            continue
        source = _find_asset_source(state.input_p, relative_asset)
        if source is None:
            unresolved.append(str(asset))
            continue
        target = Path(state.run_dir) / relative_asset
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append({
            "missing_asset": str(asset),
            "source": str(source),
            "target": str(target),
        })
    return {
        "copied_count": len(copied),
        "copied": copied,
        "unresolved": unresolved,
    }


def _restore_detail_blocks(state: Any, block_ids: list[str]) -> dict[str, Any]:
    wanted = {str(block_id) for block_id in block_ids}
    restored: list[str] = []
    for block in state.blocks:
        block_id = str(block.get("block_id", ""))
        if block_id not in wanted or block.get("status") != "discard":
            continue
        block["status"] = "keep"
        block["protected"] = True
        block["reason"] = f"{block.get('reason', '').strip()} | repair_loop restored detail-bearing block".strip(" |")
        tags = block.setdefault("risk_tags", [])
        if "repair_loop_restored_detail" not in tags:
            tags.append("repair_loop_restored_detail")
        restored.append(block_id)

    blocks_path = Path(state.run_dir) / "blocks.jsonl"
    blocks_path.write_text(
        "".join(json.dumps(block, ensure_ascii=False) + "\n" for block in state.blocks),
        encoding="utf-8",
    )
    return {
        "restored_count": len(restored),
        "restored_block_ids": restored,
    }


def _safe_relative_asset(asset: str) -> Path | None:
    text = str(asset).strip().strip("<>").replace("\\", "/")
    if not text or "://" in text or text.startswith("//"):
        return None
    path = Path(text)
    if path.is_absolute() or any(part == ".." for part in path.parts):
        return None
    return path


def _find_asset_source(input_path: Path, relative_asset: Path) -> Path | None:
    source_root = input_path.parent
    source_stem_assets = input_path.with_name(f"{input_path.stem}.assets")
    candidates = [
        source_root / relative_asset,
        source_stem_assets / relative_asset,
        source_stem_assets / relative_asset.name,
        source_root / ".assets" / relative_asset,
        source_root / ".assets" / relative_asset.name,
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _render_repair_plan(diagnosis: dict[str, Any], actions: list[dict[str, Any]]) -> str:
    lines = [
        "# KBPrep Repair Plan",
        "",
        f"- Run: `{diagnosis.get('run_id')}`",
        f"- Input: `{diagnosis.get('input_path')}`",
        f"- Iteration: {diagnosis.get('repair_iteration')} / {diagnosis.get('max_quality_iterations')}",
        "",
        "## What Failed",
        "",
    ]
    for failure_type in diagnosis.get("failure_types", []):
        lines.append(f"- `{failure_type}`")
    lines.extend(["", "## Evidence", ""])
    for error in diagnosis.get("strict_errors", []):
        lines.append(f"- {error}")
    missing_assets = diagnosis.get("evidence", {}).get("missing_assets", [])
    if missing_assets:
        lines.extend(["", "Missing assets:"])
        for asset in missing_assets:
            lines.append(f"- `{asset}`")
    discarded_ids = diagnosis.get("evidence", {}).get("discarded_detail_block_ids", [])
    if discarded_ids:
        lines.extend(["", "Discarded detail blocks:"])
        for block_id in discarded_ids:
            lines.append(f"- `{block_id}`")
    lines.extend(["", "## Repair Actions", ""])
    for action in actions:
        lines.append(f"- `{action.get('type')}`: {action.get('description')}")
    lines.extend([
        "",
        "## Rule",
        "",
        "KBPrep may only publish final Markdown after strict quality errors are cleared. Manual actions must be reviewed before rerun.",
        "",
    ])
    return "\n".join(lines)
