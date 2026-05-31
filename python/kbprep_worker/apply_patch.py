"""
apply_patch - apply guarded review patches to blocks.
Only allows changing: status, risk_tags, reason, confidence.
Cannot change: text, page_range, source_line_range.
Cannot discard protected blocks.
"""
import json
import logging
import shutil
import time
from pathlib import Path

from .envelope import ok, fail
from .quality import _detail_categories, _is_known_pollution_without_detail

logger = logging.getLogger(__name__)

# ── Allowed fields ────────────────────────────────────────────────
ALLOWED_FIELDS = {"status", "risk_tags", "reason", "confidence"}
ALLOWED_STATUSES = {"keep", "discard", "evidence", "review"}
PROTECTED_TYPES = {"operation_step", "case_step", "tool_instruction", "prompt", "code", "table"}
KEEP_TYPES = {"operation_step", "case_step", "tool_instruction", "prompt", "code", "table"}


def run(data: dict) -> None:
    run_dir = data["run_dir"]
    patch_json = data["patch_json"]

    run_p = Path(run_dir)
    blocks_path = run_p / "blocks.jsonl"
    quality_path = run_p / "quality_report.json"

    if not blocks_path.exists():
        fail("E_INPUT_NOT_FOUND", f"blocks.jsonl not found in {run_dir}")

    # Load blocks
    blocks = []
    with open(blocks_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                blocks.append(json.loads(line))

    block_map = {b["block_id"]: b for b in blocks}

    # Validate and apply patches
    applied = 0
    rejected = []

    for op in patch_json:
        op_type = op.get("op")
        path = op.get("path", "")
        value = op.get("value")

        # Parse path: /blocks/b_000123/status
        parts = path.strip("/").split("/")
        if len(parts) != 3 or parts[0] != "blocks":
            rejected.append({"op": json.dumps(op), "reason": "invalid path format"})
            continue

        block_id = parts[1]
        field = parts[2]

        # Check if block exists
        if block_id not in block_map:
            rejected.append({"op": json.dumps(op), "reason": f"block {block_id} not found"})
            continue

        block = block_map[block_id]

        # Check if field is allowed
        if field not in ALLOWED_FIELDS:
            rejected.append({"op": json.dumps(op), "reason": f"field {field} not allowed (only {ALLOWED_FIELDS})"})
            continue

        invalid_reason = _validate_patch_value(field, value, op_type)
        if invalid_reason:
            rejected.append({"op": json.dumps(op), "reason": invalid_reason})
            continue

        # Check if trying to discard a protected block
        if field == "status" and value == "discard":
            detail_categories = _detail_categories(block)
            if detail_categories and not _is_known_pollution_without_detail(block, detail_categories):
                rejected.append({
                    "op": json.dumps(op),
                    "reason": f"cannot discard detail-bearing block: {sorted(detail_categories)}",
                })
                continue
            if block.get("type") in PROTECTED_TYPES:
                rejected.append({"op": json.dumps(op), "reason": f"cannot discard protected block of type {block['type']}"})
                continue
            if block.get("protected"):
                rejected.append({"op": json.dumps(op), "reason": "cannot discard protected block"})
                continue

        # Check if trying to discard keep-types
        if field == "status" and value == "discard":
            if block.get("type") in KEEP_TYPES:
                rejected.append({"op": json.dumps(op), "reason": f"cannot discard block of type {block['type']}"})
                continue

        # Apply the patch
        if op_type == "replace":
            block[field] = value
            applied += 1
        elif op_type == "add":
            if field == "risk_tags" and isinstance(block.get("risk_tags"), list):
                block["risk_tags"].append(value)
                applied += 1
            else:
                rejected.append({"op": json.dumps(op), "reason": f"add not supported for field {field}"})
        else:
            rejected.append({"op": json.dumps(op), "reason": f"op {op_type} not supported"})

    # Re-write blocks.jsonl
    with open(blocks_path, "w", encoding="utf-8") as f:
        for block in blocks:
            f.write(json.dumps(block, ensure_ascii=False) + "\n")

    # Re-render outputs
    from . import render_outputs as render_mod
    source_hash = blocks[0].get("source_sha256", "") if blocks else ""
    run_id = run_p.name
    render_mod.render(blocks=blocks, run_dir=run_dir, source_hash=source_hash, run_id=run_id)

    previous_quality = {}
    if quality_path.exists():
        try:
            previous_quality = json.loads(quality_path.read_text(encoding="utf-8"))
        except Exception:
            previous_quality = {}
    source_type = previous_quality.get("source_type", "generic_block")
    diagnosis = _read_diagnosis(run_p)

    # Re-split chunks so cleaned output and chunk files stay consistent.
    from . import split as split_mod
    split_mod.split_into_chunks(
        blocks=blocks,
        run_dir=run_dir,
        source_type=source_type,
        source_hash=source_hash,
        run_id=run_id,
        split_strategy=diagnosis.get("split_strategy"),
    )

    # Re-run quality check
    from . import quality as qa_mod
    quality_report = qa_mod.run_quality_check(
        blocks=blocks,
        run_dir=run_dir,
        source_type=source_type,
        diagnosis=diagnosis,
    )
    quality_report["source_type"] = source_type
    for key in (
        "source_sha256",
        "config_hash",
        "plugin_version",
        "mineru_version",
        "runtime_cache_key",
        "runtime",
    ):
        if key in previous_quality:
            quality_report[key] = previous_quality[key]
    quality_report["review_applied_at"] = time.time()
    (quality_path).write_text(
        json.dumps(quality_report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    strict_errors = quality_report.get("strict_errors", [])
    latest_outputs = _run_output_paths(run_p)
    published = False
    if not strict_errors:
        output_root = _find_output_root(run_p)
        if output_root:
            latest_outputs = _publish_latest_outputs(run_p, output_root)
            _update_latest_json(output_root, run_p, latest_outputs, previous_quality, source_type)
            published = True

    ok(data={
        "ok": True,
        "applied": applied,
        "rejected": len(rejected),
        "rejected_details": rejected,
        "published": published,
        "updated_outputs": {
            "cleaned_md": str(run_p / "cleaned.md"),
            "discarded_md": str(run_p / "discarded.md"),
            "review_needed_md": str(run_p / "review_needed.md"),
            "audit_md": str(run_p / "audit.md"),
            "quality_report": str(run_p / "quality_report.json"),
        },
        "latest_outputs": latest_outputs,
    })


def _validate_patch_value(field: str, value, op_type: str) -> str | None:
    if field == "status":
        if value not in ALLOWED_STATUSES:
            return f"invalid status {value!r}; allowed: {sorted(ALLOWED_STATUSES)}"
    elif field == "risk_tags":
        if op_type == "replace":
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                return "risk_tags must be a list of strings"
        elif op_type == "add":
            if not isinstance(value, str):
                return "risk_tags add value must be a string"
    elif field == "reason":
        if not isinstance(value, str):
            return "reason must be a string"
    elif field == "confidence":
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0 or value > 1:
            return "confidence must be a number between 0 and 1"
    return None


def _find_output_root(run_p: Path) -> Path | None:
    if run_p.parent.name == "runs":
        return run_p.parent.parent
    return None


def _read_diagnosis(run_p: Path) -> dict:
    report_path = run_p / "diagnosis_report.json"
    if not report_path.exists():
        return {}
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        diagnosis = report.get("diagnosis")
        if isinstance(diagnosis, dict):
            return diagnosis
        return report if isinstance(report, dict) else {}
    except Exception:
        return {}


def _run_output_paths(run_p: Path) -> dict:
    return {
        "diagnosis_report": str(run_p / "diagnosis_report.json"),
        "blocks_jsonl": str(run_p / "blocks.jsonl"),
        "cleaned_md": str(run_p / "cleaned.md"),
        "discarded_md": str(run_p / "discarded.md"),
        "review_needed_md": str(run_p / "review_needed.md"),
        "quality_report": str(run_p / "quality_report.json"),
        "parts_dir": str(run_p / "parts"),
    }


def _publish_latest_outputs(run_p: Path, output_root: Path) -> dict:
    output_root.mkdir(parents=True, exist_ok=True)
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
        src = run_p / name
        dst = output_root / name
        if src.exists():
            shutil.copy2(str(src), str(dst))
        elif name == "review_pack.json" and dst.exists():
            dst.unlink()

    src_parts = run_p / "parts"
    dst_parts = output_root / "parts"
    if dst_parts.exists():
        shutil.rmtree(dst_parts)
    if src_parts.exists():
        shutil.copytree(src_parts, dst_parts)
    else:
        dst_parts.mkdir(parents=True, exist_ok=True)

    src_images = run_p / "images"
    dst_images = output_root / "images"
    if dst_images.exists():
        shutil.rmtree(dst_images)
    if src_images.exists():
        shutil.copytree(src_images, dst_images)
    else:
        dst_images.mkdir(parents=True, exist_ok=True)

    return {
        "converted_md": str(output_root / "converted.md"),
        "diagnosis_report": str(output_root / "diagnosis_report.json"),
        "blocks_jsonl": str(output_root / "blocks.jsonl"),
        "cleaned_md": str(output_root / "cleaned.md"),
        "discarded_md": str(output_root / "discarded.md"),
        "review_needed_md": str(output_root / "review_needed.md"),
        "quality_report": str(output_root / "quality_report.json"),
        "conversion_report": str(output_root / "conversion_report.json"),
        "audit_md": str(output_root / "audit.md"),
        "parts_dir": str(output_root / "parts"),
        "images_dir": str(output_root / "images"),
        "review_pack": str(output_root / "review_pack.json"),
    }


def _update_latest_json(
    output_root: Path,
    run_p: Path,
    latest_outputs: dict,
    previous_quality: dict,
    source_type: str,
) -> None:
    latest_path = output_root / "latest.json"
    latest = {}
    if latest_path.exists():
        try:
            latest = json.loads(latest_path.read_text(encoding="utf-8"))
        except Exception:
            latest = {}
    latest.update({
        "run_id": run_p.name,
        "run_dir": str(run_p),
        "source_type": source_type,
        "source_sha256": previous_quality.get("source_sha256", latest.get("source_sha256", "")),
        "latest_outputs": latest_outputs,
        "review_applied_at": time.time(),
    })
    latest_path.write_text(json.dumps(latest, indent=2, ensure_ascii=False), encoding="utf-8")
