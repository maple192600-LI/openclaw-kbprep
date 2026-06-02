"""Cleanup lifecycle management for kbprep artifacts.

The source file and source-side final Markdown are user assets. Everything
under output_root is treated as temporary audit/process material unless the
user intentionally keeps it.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

from .envelope import fail, ok


TOP_LEVEL_FILES = [
    "converted.md",
    "diagnosis_report.json",
    "blocks.jsonl",
    "cleaned.md",
    "discarded.md",
    "review_needed.md",
    "quality_report.json",
    "conversion_report.json",
    "audit.md",
    "review_pack.json",
    "latest.json",
    "batch_inventory.json",
    "progress.json",
    "failures.json",
    "results.json",
]

TOP_LEVEL_DIRS = [
    "original",
    "runs",
    "parts",
    "images",
    "obsidian",
    "files",
]


def run(data: dict) -> None:
    output_root = Path(data["output_root"])
    action = data.get("action", "finalize")
    dry_run = bool(data.get("dry_run", False))
    confirm_review_needed = bool(data.get("confirm_review_needed", False))
    older_than_days = float(data.get("older_than_days", 7))

    if action not in {"finalize", "expired", "all"}:
        fail(
            "E_INVALID_INPUT",
            f"Unsupported cleanup action: {action}",
            details={"allowed_actions": ["finalize", "expired", "all"]},
        )

    if not output_root.exists() or not output_root.is_dir():
        fail("E_INVALID_INPUT", f"output_root does not exist or is not a directory: {output_root}")

    root = output_root.resolve()

    if action == "finalize":
        if (root / "results.json").exists() and not (root / "latest.json").exists():
            result = _finalize_batch(root, confirm_review_needed=confirm_review_needed, dry_run=dry_run)
        else:
            result = _finalize_single(root, confirm_review_needed=confirm_review_needed, dry_run=dry_run)
    elif action == "expired":
        result = _cleanup_expired(root, older_than_days=older_than_days, dry_run=dry_run)
    else:
        result = _cleanup_all(root, dry_run=dry_run)

    ok(data=result)


def _finalize_single(root: Path, *, confirm_review_needed: bool, dry_run: bool) -> dict:
    latest_path = root / "latest.json"
    if not latest_path.exists():
        fail(
            "KBPREP_NO_SUCCESSFUL_RUN",
            "No latest.json found. Run kbprep_prepare successfully before finalizing cleanup.",
            details={"output_root": str(root)},
        )

    latest = _read_json(latest_path)
    latest_outputs = latest.get("latest_outputs", {})
    final_md_raw = latest_outputs.get("final_md")
    source_path = latest.get("input_path")
    review_needed = root / "review_needed.md"

    if not final_md_raw:
        fail(
            "KBPREP_FINAL_OUTPUT_MISSING",
            "latest.json does not record a source-side final Markdown path. Cleanup stopped.",
            details={"latest_json": str(latest_path), "output_root": str(root)},
        )
    final_md = Path(final_md_raw)
    if not final_md.exists():
        fail(
            "KBPREP_FINAL_OUTPUT_MISSING",
            "Final source-side Markdown is missing. Cleanup stopped to avoid deleting audit evidence.",
            details={"final_md": str(final_md), "output_root": str(root)},
        )

    if _has_review_content(review_needed) and not confirm_review_needed:
        fail(
            "KBPREP_REVIEW_NEEDED",
            "review_needed.md still has content. Confirm cleanup only after you accept the result.",
            details={"review_needed_md": str(review_needed)},
            suggested_action="Inspect review_needed.md, then rerun cleanup with confirm_review_needed=true if you accept it.",
        )

    manifest = {
        "schema": "kbprep.cleanup_manifest.v1",
        "status": "finalized",
        "finalized_at": time.time(),
        "source_path": source_path,
        "source_sha256": latest.get("source_sha256"),
        "source_type": latest.get("source_type"),
        "final_md": str(final_md),
        "final_assets_dir": latest_outputs.get("final_assets_dir"),
        "run_id": latest.get("run_id"),
        "plugin_version": latest.get("plugin_version"),
        "runtime_cache_key": latest.get("runtime_cache_key"),
    }

    deleted = _delete_standard_artifacts(root, dry_run=dry_run)
    manifest_path = root / "kbprep_manifest.json"
    if not dry_run:
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "action": "finalize",
        "output_root": str(root),
        "final_md": str(final_md),
        "manifest": str(manifest_path),
        "deleted": deleted,
        "dry_run": dry_run,
    }


def _finalize_batch(root: Path, *, confirm_review_needed: bool, dry_run: bool) -> dict:
    results_path = root / "results.json"
    results = _read_json(results_path)
    if not isinstance(results, list):
        fail("KBPREP_INVALID_STATE", "results.json is not a batch results array.", details={"results_json": str(results_path)})

    finalized: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    review_needed: list[str] = []
    for entry in results:
        if not isinstance(entry, dict) or not entry.get("ok"):
            continue
        final_md = entry.get("batch_final_md") or entry.get("latest_outputs", {}).get("final_md")
        output_root = Path(entry.get("output_root", ""))
        if not final_md or not Path(final_md).exists():
            missing.append({"file": entry.get("relative_path") or entry.get("file"), "final_md": final_md})
        review_path = output_root / "review_needed.md"
        if _has_review_content(review_path):
            review_needed.append(str(review_path))
        finalized.append({
            "file": entry.get("relative_path") or entry.get("file"),
            "final_md": final_md,
            "run_id": entry.get("run_id"),
        })

    if missing:
        fail(
            "KBPREP_FINAL_OUTPUT_MISSING",
            "Some batch final Markdown files are missing. Cleanup stopped.",
            details={"missing": missing[:20], "missing_count": len(missing)},
        )
    if review_needed and not confirm_review_needed:
        fail(
            "KBPREP_REVIEW_NEEDED",
            "Some batch files still have review_needed.md content. Confirm cleanup only after you accept the results.",
            details={"review_needed": review_needed[:20], "review_needed_count": len(review_needed)},
        )

    manifest = {
        "schema": "kbprep.batch_cleanup_manifest.v1",
        "status": "finalized",
        "finalized_at": time.time(),
        "total_finalized": len(finalized),
        "finalized": finalized,
    }
    deleted = _delete_standard_artifacts(root, dry_run=dry_run)
    manifest_path = root / "kbprep_batch_manifest.json"
    if not dry_run:
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "action": "finalize",
        "output_root": str(root),
        "manifest": str(manifest_path),
        "finalized": finalized,
        "deleted": deleted,
        "dry_run": dry_run,
    }


def _cleanup_expired(root: Path, *, older_than_days: float, dry_run: bool) -> dict:
    cutoff = time.time() - max(0.0, older_than_days) * 86400
    deleted: list[str] = []
    runs_dir = root / "runs"
    if runs_dir.exists():
        for child in runs_dir.iterdir():
            if child.is_dir() and child.stat().st_mtime < cutoff:
                _delete_path(root, child, deleted, dry_run=dry_run)

    files_dir = root / "files"
    if files_dir.exists():
        for child in files_dir.iterdir():
            runs = child / "runs"
            if runs.exists():
                for run_dir in runs.iterdir():
                    if run_dir.is_dir() and run_dir.stat().st_mtime < cutoff:
                        _delete_path(root, run_dir, deleted, dry_run=dry_run)

    return {
        "action": "expired",
        "output_root": str(root),
        "older_than_days": older_than_days,
        "deleted": deleted,
        "dry_run": dry_run,
    }


def _cleanup_all(root: Path, *, dry_run: bool) -> dict:
    deleted = _delete_standard_artifacts(root, dry_run=dry_run)
    return {
        "action": "all",
        "output_root": str(root),
        "deleted": deleted,
        "dry_run": dry_run,
    }


def _delete_standard_artifacts(root: Path, *, dry_run: bool) -> list[str]:
    deleted: list[str] = []
    for name in TOP_LEVEL_FILES:
        _delete_path(root, root / name, deleted, dry_run=dry_run)
    for name in TOP_LEVEL_DIRS:
        _delete_path(root, root / name, deleted, dry_run=dry_run)
    return deleted


def _delete_path(root: Path, path: Path, deleted: list[str], *, dry_run: bool) -> None:
    if not path.exists():
        return
    resolved = path.resolve()
    if resolved != root and root not in resolved.parents:
        raise RuntimeError(f"Refusing to delete outside output_root: {resolved}")
    deleted.append(str(resolved))
    if dry_run:
        return
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def _has_review_content(path: Path) -> bool:
    if not path.exists():
        return False
    return bool(path.read_text(encoding="utf-8").strip())


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail("KBPREP_INVALID_STATE", f"Invalid JSON file: {path}", details={"error": str(exc)})
