"""Latest-output and retention helpers for prepare."""

from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path

from .prepare_publish import (
    publish_direct_final_to_source,
    source_final_assets_dir,
    source_final_markdown_path,
)

logger = logging.getLogger(__name__)


def latest_output_paths(root_p: Path, input_p: Path | None = None, profile: str = "standard") -> dict:
    """Return stable top-level paths for the latest successful run."""
    source_side_final = profile != "curated_obsidian_kb"
    final_artifact_type = "markdown" if source_side_final else "obsidian_dir"
    final_md = (source_final_markdown_path(input_p) if input_p else root_p / "cleaned.md") if source_side_final else None
    final_assets_dir = (source_final_assets_dir(input_p) if input_p else root_p / "images") if source_side_final else None
    obsidian_dir = root_p / "obsidian"
    obsidian_index = obsidian_dir / "00-索引.md"
    review_pack = root_p / "review_pack.json"
    return {
        "converted_md": str(root_p / "converted.md"),
        "diagnosis_report": str(root_p / "diagnosis_report.json"),
        "blocks_jsonl": str(root_p / "blocks.jsonl"),
        "cleaned_md": str(root_p / "cleaned.md"),
        "final_artifact_type": final_artifact_type,
        "final_md": str(final_md) if final_md else None,
        "final_assets_dir": str(final_assets_dir) if final_assets_dir else None,
        "discarded_md": str(root_p / "discarded.md"),
        "review_needed_md": str(root_p / "review_needed.md"),
        "quality_report": str(root_p / "quality_report.json"),
        "conversion_report": str(root_p / "conversion_report.json"),
        "audit_md": str(root_p / "audit.md"),
        "parts_dir": str(root_p / "parts"),
        "images_dir": str(root_p / "images"),
        "obsidian_dir": str(obsidian_dir) if obsidian_dir.exists() else None,
        "obsidian_index": str(obsidian_index) if obsidian_index.exists() else None,
        "review_pack": str(review_pack) if review_pack.exists() else None,
    }


def publish_latest_outputs(run_dir: Path, root_p: Path, input_p: Path, profile: str = "standard") -> dict:
    """Copy successful run artifacts to output_root for direct reading."""
    root_p.mkdir(parents=True, exist_ok=True)
    for name in [
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
    ]:
        src = run_dir / name
        dst = root_p / name
        if src.exists():
            shutil.copy2(str(src), str(dst))
        elif dst.exists() and name == "review_pack.json":
            dst.unlink()

    if profile != "curated_obsidian_kb":
        publish_direct_final_to_source(run_dir, input_p)

    src_parts = run_dir / "parts"
    dst_parts = root_p / "parts"
    if dst_parts.exists():
        shutil.rmtree(dst_parts)
    if src_parts.exists():
        shutil.copytree(src_parts, dst_parts)
    else:
        dst_parts.mkdir(parents=True, exist_ok=True)

    src_images = run_dir / "images"
    dst_images = root_p / "images"
    if dst_images.exists():
        shutil.rmtree(dst_images)
    if src_images.exists():
        shutil.copytree(src_images, dst_images)
    else:
        dst_images.mkdir(parents=True, exist_ok=True)

    src_obsidian = run_dir / "obsidian"
    dst_obsidian = root_p / "obsidian"
    if dst_obsidian.exists():
        shutil.rmtree(dst_obsidian)
    if src_obsidian.exists():
        shutil.copytree(src_obsidian, dst_obsidian)

    return latest_output_paths(root_p, input_p, profile)


def apply_artifact_policy(root_p: Path, current_run_dir: Path, artifact_policy: str) -> None:
    if artifact_policy == "keep_all":
        return
    if artifact_policy not in {"keep_latest", "final_only"}:
        artifact_policy = "keep_latest"

    runs_dir = root_p / "runs"
    if not runs_dir.exists():
        return

    keep_count = 1 if artifact_policy == "final_only" else 3
    max_age_seconds = 7 * 86400
    now = time.time()
    run_dirs = sorted(
        [p for p in runs_dir.iterdir() if p.is_dir()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    keep = {current_run_dir.resolve()}
    for run_dir in run_dirs[:keep_count]:
        keep.add(run_dir.resolve())

    for run_dir in run_dirs:
        try:
            is_current = run_dir.resolve() == current_run_dir.resolve()
            is_expired = (now - run_dir.stat().st_mtime) > max_age_seconds
            if (run_dir.resolve() not in keep or is_expired) and not is_current:
                shutil.rmtree(run_dir)
        except Exception as exc:
            logger.warning("Failed to prune old run %s: %s", run_dir, exc)
