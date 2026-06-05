"""Directory batch processing with sample-first safety."""
import gc
import hashlib
import json
import logging
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .envelope import ok, fail
from .supported_formats import BATCH_SUPPORTED_EXTENSIONS, FORMAT_BY_EXTENSION, MEDIA_EXTENSIONS, MINERU_EXTENSIONS

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = BATCH_SUPPORTED_EXTENSIONS
HEAVY_CONVERSION_EXTENSIONS = MINERU_EXTENSIONS

DEFAULT_MIN_FREE_GB = 4.0

IGNORED_DIRECTORY_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".cache",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "coverage",
    ".next",
    ".nuxt",
}


def _available_memory_gb() -> float:
    try:
        import psutil
        return psutil.virtual_memory().available / (1024**3)
    except ImportError:
        return 999.0


def _process_one_file(file_path: Path, output_root: str, profile: str,
                      language: str, mode: str, force: bool, artifact_policy: str = "keep_latest") -> dict:
    payload = {
        "input_path": str(file_path),
        "output_root": output_root,
        "profile": profile,
        "mode": mode,
        "language": language,
        "source_type": "auto",
        "splitter": "auto",
        "force": force,
        "artifact_policy": artifact_policy,
    }
    proc = subprocess.run(
        [sys.executable, "-m", "kbprep_worker.cli", "prepare", "--json-stdin"],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        cwd=str(Path(__file__).resolve().parents[1]),
        timeout=5400,
    )
    stdout = proc.stdout.strip()
    if not stdout:
        return {
            "ok": False,
            "error": {
                "code": "E_WORKER_BAD_JSON",
                "message": "No stdout from prepare subprocess",
                "stderr_tail": proc.stderr.splitlines()[-20:],
            },
        }
    try:
        return json.loads(stdout.splitlines()[-1])
    except json.JSONDecodeError as exc:
        return {
            "ok": False,
            "error": {
                "code": "E_WORKER_BAD_JSON",
                "message": str(exc),
                "stdout_preview": stdout[:500],
                "stderr_tail": proc.stderr.splitlines()[-20:],
            },
        }


def _safe_output_dir_name(file_path: Path) -> str:
    stem = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "_", file_path.stem).strip("._-")
    if not stem:
        stem = "source"
    digest = hashlib.sha256(str(file_path.resolve()).encode("utf-8")).hexdigest()[:8]
    return f"{stem}_{digest}"


def _output_root_for_file(batch_output_root: Path, file_path: Path) -> Path:
    return batch_output_root / "files" / _safe_output_dir_name(file_path)


def _batch_final_fields_from_result(data: dict) -> dict:
    latest_outputs = data.get("latest_outputs", {})
    if not isinstance(latest_outputs, dict):
        return {}
    artifact_type = latest_outputs.get("final_artifact_type")
    final_md = latest_outputs.get("final_md")
    if artifact_type == "markdown" or final_md:
        if final_md and Path(final_md).exists():
            return {
                "final_artifact_type": "markdown",
                "batch_final_md": final_md,
            }
        return {}

    obsidian_dir = latest_outputs.get("obsidian_dir")
    obsidian_index = latest_outputs.get("obsidian_index")
    obsidian_complete = latest_outputs.get("obsidian_complete")
    if artifact_type == "obsidian_dir" or obsidian_dir or obsidian_index:
        if obsidian_dir and obsidian_index and Path(obsidian_dir).is_dir() and Path(obsidian_index).is_file():
            fields = {
                "final_artifact_type": "obsidian_dir",
                "batch_obsidian_dir": obsidian_dir,
                "batch_obsidian_index": obsidian_index,
            }
            if obsidian_complete and Path(obsidian_complete).is_file():
                fields["batch_obsidian_complete"] = obsidian_complete
            return fields
    return {}


def _write_progress(output_root: Path, payload: dict) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "progress.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _write_failures(output_root: Path, failures: list[dict]) -> None:
    (output_root / "failures.json").write_text(
        json.dumps(failures, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _scan_input_files(input_p: Path) -> tuple[list[Path], dict]:
    files: list[Path] = []
    entries: list[dict] = []
    skipped_unsupported = 0

    for file_path in _iter_source_files(input_p):
        ext = file_path.suffix.lower()
        detected_format = FORMAT_BY_EXTENSION.get(ext, "unknown")
        relative_path = file_path.relative_to(input_p).as_posix()
        entry = {
            "file": file_path.name,
            "relative_path": relative_path,
            "extension": ext,
            "detected_format": detected_format,
            "size_bytes": file_path.stat().st_size,
            "conversion_weight": "heavy" if _is_heavy_conversion_file(file_path) else "light",
        }
        if ext in SUPPORTED_EXTENSIONS:
            entry["action"] = "process"
            files.append(file_path)
        else:
            entry["action"] = "skip"
            skipped_unsupported += 1
            if ext in MEDIA_EXTENSIONS:
                entry["reason"] = "media_binary_not_transcribed_in_v1"
            else:
                entry["reason"] = f"unsupported_extension:{ext or '<none>'}"
        entries.append(entry)

    inventory = {
        "input_dir": str(input_p),
        "discovered_total": len(entries),
        "processable_total": len(files),
        "skipped_unsupported": skipped_unsupported,
        "files": entries,
    }
    return files, inventory


def _iter_source_files(root: Path):
    for child in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if child.is_symlink():
            continue
        if child.is_dir():
            if child.name.lower() in IGNORED_DIRECTORY_NAMES:
                continue
            yield from _iter_source_files(child)
        elif child.is_file():
            yield child


def _write_batch_inventory(output_root: Path, inventory: dict) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    path = output_root / "batch_inventory.json"
    path.write_text(json.dumps(inventory, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _is_heavy_conversion_file(file_path: Path) -> bool:
    return file_path.suffix.lower() in HEAVY_CONVERSION_EXTENSIONS


def run(data: dict) -> None:
    input_dir = data["input_dir"]
    output_root = data["output_root"]
    profile = data.get("profile", "curated_obsidian_kb")
    language = data.get("language", "zh")
    mode = data.get("mode", "rules_only")
    force = data.get("force", False)
    artifact_policy = data.get("artifact_policy", "keep_latest")
    min_free_gb = data.get("min_free_memory_gb", DEFAULT_MIN_FREE_GB)
    convert_jobs = int(data.get("convert_jobs", 1))

    input_p = Path(input_dir)
    output_p = Path(output_root)
    if not input_p.exists() or not input_p.is_dir():
        fail("E_INVALID_INPUT", f"input_dir does not exist or is not a directory: {input_dir}")

    files, inventory = _scan_input_files(input_p)
    inventory_path = _write_batch_inventory(output_p, inventory)
    if not files:
        fail(
            "E_INVALID_INPUT",
            f"No supported files found in {input_dir}",
            details={
                "batch_inventory_json": str(inventory_path),
                "discovered_total": inventory["discovered_total"],
                "skipped_unsupported": inventory["skipped_unsupported"],
            },
        )

    available = _available_memory_gb()
    if available < min_free_gb:
        gc.collect()
        available = _available_memory_gb()
        if available < min_free_gb / 2:
            fail("KBPREP_OOM_RISK",
                 f"Insufficient memory ({available:.1f} GB free, need {min_free_gb:.1f} GB).",
                 details={"available_gb": round(available, 1)})

    started_at = time.time()
    results: list[dict] = []
    failures: list[dict] = []
    relative_paths = {file_path: file_path.relative_to(input_p).as_posix() for file_path in files}

    sample = files[0]
    sample_relative_path = relative_paths[sample]
    _write_progress(output_p, {
        "stage": "sample",
        "total": len(files),
        "discovered_total": inventory["discovered_total"],
        "skipped_unsupported": inventory["skipped_unsupported"],
        "processed": 0,
        "sample_file": sample_relative_path,
        "started_at": started_at,
    })
    sample_output_root = _output_root_for_file(output_p, sample)
    sample_result = _process_one_file(sample, str(sample_output_root), profile, language, mode, force, artifact_policy)
    sample_data = sample_result.get("data", {})
    sample_entry = {
        "file": sample.name,
        "relative_path": sample_relative_path,
        "output_root": str(sample_output_root),
        **sample_data,
        "ok": sample_result.get("ok", False),
    }
    if sample_result.get("ok") and not sample_data.get("strict_errors"):
        sample_entry.update(_batch_final_fields_from_result(sample_data))
    results.append(sample_entry)
    if not sample_result.get("ok") or sample_result.get("data", {}).get("strict_errors"):
        failures.append({
            "file": sample.name,
            "relative_path": sample_relative_path,
            "output_root": str(sample_output_root),
            "error": sample_result.get("error", {}),
            "data": sample_result.get("data", {}),
        })
        _write_failures(output_p, failures)
        _write_progress(output_p, {
            "stage": "stopped_after_sample",
            "total": len(files),
            "discovered_total": inventory["discovered_total"],
            "skipped_unsupported": inventory["skipped_unsupported"],
            "processed": 1,
            "failed": 1,
            "started_at": started_at,
            "finished_at": time.time(),
        })
        fail("E_QA_FAILED", "Sample file failed. Batch stopped before processing remaining files.",
             details={"sample": sample.name, "result": sample_result}, warnings=sample_result.get("warnings", []))

    remaining = files[1:]
    succeeded = 1
    skipped = 1 if sample_result.get("data", {}).get("skipped") else 0
    failed = 0
    heavy_files = [file_path for file_path in files if _is_heavy_conversion_file(file_path)]
    heavy_remaining = [file_path for file_path in remaining if _is_heavy_conversion_file(file_path)]
    light_remaining = [file_path for file_path in remaining if not _is_heavy_conversion_file(file_path)]

    def record_result(f: Path, out: dict) -> None:
        nonlocal succeeded, skipped, failed

        if out.get("ok") and not out.get("data", {}).get("strict_errors"):
            succeeded += 1
            if out.get("data", {}).get("skipped"):
                skipped += 1
            file_output_root = _output_root_for_file(output_p, f)
            out_data = out.get("data", {})
            entry = {
                "file": f.name,
                "relative_path": relative_paths[f],
                "output_root": str(file_output_root),
                **out_data,
                "ok": True,
            }
            entry.update(_batch_final_fields_from_result(out_data))
            results.append(entry)
        else:
            failed += 1
            file_output_root = _output_root_for_file(output_p, f)
            failure = {
                "file": f.name,
                "relative_path": relative_paths[f],
                "output_root": str(file_output_root),
                "error": out.get("error", {}),
                "data": out.get("data", {}),
            }
            failures.append(failure)
            results.append({"file": f.name, "ok": False, **failure})

        _write_progress(output_p, {
            "stage": "batch",
            "total": len(files),
            "discovered_total": inventory["discovered_total"],
            "skipped_unsupported": inventory["skipped_unsupported"],
            "processed": len(results),
            "succeeded": succeeded,
            "skipped": skipped,
            "failed": failed,
            "heavy_conversion_files": len(heavy_files),
            "heavy_conversion_concurrency": 1,
            "light_conversion_concurrency": max(1, min(convert_jobs, len(light_remaining) or 1)),
            "started_at": started_at,
            "updated_at": time.time(),
        })
        _write_failures(output_p, failures)

    # MinerU/OCR-style conversions are intentionally serialized to avoid GPU/CPU
    # memory spikes. Lightweight text/code/XML conversions may use convert_jobs.
    for f in heavy_remaining:
        try:
            out = _process_one_file(
                f,
                str(_output_root_for_file(output_p, f)),
                profile,
                language,
                mode,
                force,
                artifact_policy,
            )
        except Exception as exc:
            out = {"ok": False, "error": {"message": str(exc)}}
        record_result(f, out)

    max_workers = max(1, min(convert_jobs, len(light_remaining) or 1))
    if light_remaining:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_file = {
                executor.submit(
                    _process_one_file,
                    f,
                    str(_output_root_for_file(output_p, f)),
                    profile,
                    language,
                    mode,
                    force,
                    artifact_policy,
                ): f
                for f in light_remaining
            }
            for future in as_completed(future_to_file):
                f = future_to_file[future]
                try:
                    out = future.result()
                except Exception as exc:
                    out = {"ok": False, "error": {"message": str(exc)}}
                record_result(f, out)

    _write_progress(output_p, {
        "stage": "complete",
        "total": len(files),
        "discovered_total": inventory["discovered_total"],
        "skipped_unsupported": inventory["skipped_unsupported"],
        "processed": len(results),
        "succeeded": succeeded,
        "skipped": skipped,
        "failed": failed,
        "started_at": started_at,
        "finished_at": time.time(),
    })
    _write_failures(output_p, failures)
    (output_p / "results.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    ok(data={
        "ok": failed == 0,
        "total": len(files),
        "discovered_total": inventory["discovered_total"],
        "succeeded": succeeded,
        "skipped": skipped,
        "skipped_unsupported": inventory["skipped_unsupported"],
        "failed": failed,
        "heavy_conversion_files": len(heavy_files),
        "heavy_conversion_concurrency": 1,
        "light_conversion_concurrency": max_workers,
        "results": results,
        "batch_inventory_json": str(inventory_path),
        "failures_json": str(output_p / "failures.json"),
        "progress_json": str(output_p / "progress.json"),
        "results_json": str(output_p / "results.json"),
        "files_dir": str(output_p / "files"),
    })
