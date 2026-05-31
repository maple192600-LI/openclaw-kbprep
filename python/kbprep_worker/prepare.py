"""
prepare - single-file pipeline.

Pipeline: env_check -> original_preserve -> diagnose -> convert -> normalize
-> blockify -> classify_blocks -> clean_rules -> image_clean -> render_outputs
-> split -> quality_check

Each stage failure is tracked. If any stage fails, subsequent stages are skipped.
"""
import hashlib
import csv
import io
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from html.parser import HTMLParser
from pathlib import Path

from . import __version__
from .envelope import ok, fail
from .supported_formats import (
    CODE_EXTENSIONS,
    CODE_LANGUAGE_BY_EXTENSION,
    DIRECT_EXTENSIONS,
    EPUB_EXTENSIONS,
    FORMAT_BY_EXTENSION,
    MEDIA_EXTENSIONS,
    NOTEBOOK_EXTENSIONS,
    OFFICE_XML_EXTENSIONS,
)

logger = logging.getLogger(__name__)

class PipelineError(Exception):
    """Raised when a pipeline stage fails."""
    def __init__(self, code: str, message: str, details: dict = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


def _stderr_log(level: str, stage: str, message: str, code: str = "") -> None:
    """Write a JSONL log entry to stderr."""
    entry = {"level": level, "stage": stage, "message": message}
    if code:
        entry["code"] = code
    sys.stderr.write(json.dumps(entry, ensure_ascii=False) + "\n")
    sys.stderr.flush()


def run(data: dict) -> None:
    input_path = data["input_path"]
    output_root = data.get("output_root", ".")
    profile = data.get("profile", "standard")
    mode = data.get("mode", "rules_only")
    force = data.get("force", False)
    language = data.get("language", "zh")
    override_source_type = data.get("source_type", "auto")
    override_splitter = data.get("splitter", "auto")

    warnings: list[str] = []
    strict_errors: list[str] = []
    input_p = Path(input_path)
    root_p = Path(output_root)

    if not input_p.exists():
        fail("E_INPUT_NOT_FOUND", f"Input file does not exist: {input_path}")
        return

    try:
        # Stage 1: env_check
        _stderr_log("info", "env_check", "Checking environment")
        env_warnings = _check_env(profile)
        warnings.extend(env_warnings)
        # Stage 2: original_preserve
        _stderr_log("info", "original_preserve", "Computing file hash")
        file_bytes = input_p.read_bytes()
        file_hash = hashlib.sha256(file_bytes).hexdigest()
        file_size = len(file_bytes)

        plugin_version = __version__
        mineru_version = _get_mineru_version()
        python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        runtime = _runtime_snapshot(mineru_version)
        runtime_cache_key = _runtime_cache_key(runtime)

        from .detect import detect_source_type
        source_type = override_source_type if override_source_type != "auto" else detect_source_type(input_path)
        config_str = json.dumps({
            "source_type": source_type,
            "language": language,
            "mode": mode,
            "splitter": override_splitter,
            "profile": profile,
        }, sort_keys=True)
        config_hash = hashlib.sha256(config_str.encode()).hexdigest()[:16]

        run_hash_input = f"{file_hash}:{config_hash}:{plugin_version}:{runtime_cache_key}"
        run_hash = hashlib.sha256(run_hash_input.encode()).hexdigest()
        run_id = f"{time.strftime('%Y%m%d_%H%M%S')}_{run_hash[:12]}"

        original_dir = root_p / "original"
        runs_dir = root_p / "runs"
        run_dir = runs_dir / run_id
        latest_file = root_p / "latest.json"

        # Check for existing run
        if not force:
            existing = _find_existing_run(root_p, file_hash, config_hash, plugin_version, runtime_cache_key)
            if existing:
                _stderr_log("info", "original_preserve", f"Skipping: matching run {existing['run_id']}")
                ok(data={
                    "ok": True,
                    "run_id": existing["run_id"],
                    "run_dir": existing["run_dir"],
                    "skipped": True,
                    "warnings": ["Already processed with same config. Use force=true to re-process."],
                    "strict_errors": [],
                })
                return

        # Create directories
        original_dir.mkdir(parents=True, exist_ok=True)
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "evidence").mkdir(exist_ok=True)
        (run_dir / "chunks").mkdir(exist_ok=True)
        (run_dir / "logs").mkdir(exist_ok=True)

        # Store original
        original_file = original_dir / f"{file_hash[:16]}{input_p.suffix}"
        if not original_file.exists():
            shutil.copy2(str(input_p), str(original_file))
            _stderr_log("info", "original_preserve", f"Original saved: {original_file.name}")
        # Stage 3: diagnose
        _stderr_log("info", "diagnose", "Diagnosing file quality")
        diagnosis = {}
        try:
            diag_envelope = _run_diagnose_subprocess(input_path, output_root, override_source_type)
            if diag_envelope.get("ok"):
                diagnosis = diag_envelope.get("data", {})
                warnings.extend(diagnosis.get("warnings", []))
            else:
                warnings.append(f"Diagnosis failed: {diag_envelope.get('error', {}).get('message', 'unknown')}")
        except Exception as e:
            warnings.append(f"Diagnosis error: {e}")
            _stderr_log("warn", "diagnose", str(e))

        _write_diagnosis_report(
            run_dir=run_dir,
            input_path=input_p,
            file_hash=file_hash,
            source_type=source_type,
            diagnosis=diagnosis,
            runtime=runtime,
            warnings=warnings,
        )
        # Stage 4: convert
        _stderr_log("info", "convert", "Converting file")
        converted_path = run_dir / "converted.md"
        mineru_artifacts = {}

        ext = input_p.suffix.lower()
        direct_exts = DIRECT_EXTENSIONS
        media_exts = MEDIA_EXTENSIONS
        office_xml_exts = OFFICE_XML_EXTENSIONS

        if ext in direct_exts:
            text = _read_direct_source(input_p)
            converted_path.write_text(text, encoding="utf-8")
            _stderr_log("info", "convert", "Text-like file normalized directly")
        elif ext in office_xml_exts:
            _validate_convertible_container(input_p)
            text, office_warnings = _office_xml_to_markdown(input_p)
            converted_path.write_text(text, encoding="utf-8")
            warnings.extend(office_warnings)
            _stderr_log("info", "convert", "Office XML converted directly")
        elif ext in EPUB_EXTENSIONS:
            _validate_convertible_container(input_p)
            from .epub import convert_epub
            result, epub_warnings = convert_epub(input_p, converted_path)
            mineru_artifacts = result
            warnings.extend(epub_warnings)
            _stderr_log("info", "convert", "EPUB XHTML converted directly")
        elif ext in media_exts:
            raise PipelineError(
                "E_UNSUPPORTED_TYPE",
                "Audio/video binaries are not transcribed in v1. Provide a local subtitle, transcript, or ASR text file.",
                {"extension": ext},
            )
        elif ext == ".pdf" and diagnosis.get("conversion_strategy") in {"pdf_text_layer", "pdf_text_layer_slide_order"}:
            from . import pdf_text
            result = pdf_text.convert_text_layer_pdf(input_p, converted_path, run_dir)
            mineru_artifacts = result
            warnings.extend(result.get("warnings", []))
            _stderr_log("info", "convert", "PDF text layer converted directly")
            fallback = _maybe_fallback_pdf_text_layer_to_mineru(
                input_p=input_p,
                converted_path=converted_path,
                run_dir=run_dir,
                language=language,
                text_layer_artifacts=result,
            )
            if fallback:
                mineru_artifacts = fallback
                warnings.extend(fallback.get("warnings", []))
                _stderr_log("warn", "convert", "PDF text layer was unreadable; fell back to MinerU OCR")
        else:
            result = _run_mineru_conversion(
                input_p=input_p,
                converted_path=converted_path,
                run_dir=run_dir,
                language=language,
                mode="auto",
            )
            mineru_artifacts = result
            warnings.extend(result.get("warnings", []))
            _stderr_log("info", "convert", "MinerU conversion complete")

        if not converted_path.exists():
            raise PipelineError("E_CONVERT_OUTPUT_MISSING", "converted.md not found after conversion")

        _stderr_log("info", "convert", f"Converted file size: {converted_path.stat().st_size} bytes")
        _write_conversion_report(
            run_dir=run_dir,
            input_path=input_p,
            output_path=converted_path,
            converter=(
                "direct_code" if ext in CODE_EXTENSIONS
                else "notebook_json" if ext in NOTEBOOK_EXTENSIONS
                else "direct_text" if ext in direct_exts
                else "office_xml" if ext in office_xml_exts
                else "epub_xhtml" if mineru_artifacts.get("converter") == "epub_xhtml"
                else "mineru_after_pdf_text_layer_fallback" if mineru_artifacts.get("fallback_from") == "pdf_text_layer"
                else "pdf_text_layer" if mineru_artifacts.get("converter") == "pdf_text_layer"
                else "mineru"
            ),
            source_type=source_type,
            mineru_artifacts=mineru_artifacts,
            runtime=runtime,
            diagnosis=diagnosis,
            warnings=warnings,
        )
        # Stage 5: normalize
        _stderr_log("info", "normalize", "Normalizing markdown")
        normalized_path = run_dir / "normalized.md"
        from . import normalize as norm_mod
        norm_result = norm_mod.normalize(
            converted_text=converted_path.read_text(encoding="utf-8"),
            run_dir=str(run_dir),
            mineru_artifacts=mineru_artifacts,
        )
        normalized_path.write_text(norm_result["normalized_text"], encoding="utf-8")
        warnings.extend(norm_result.get("warnings", []))
        _stderr_log("info", "normalize", f"Normalized: {norm_result.get('fix_count', 0)} fixes applied")

        if not normalized_path.exists():
            raise PipelineError("E_NORMALIZE_FAILED", "normalized.md not found after normalization")
        # Stage 6: blockify
        _stderr_log("info", "blockify", "Building blocks")
        blocks_path = run_dir / "blocks.jsonl"
        from . import blockify as block_mod
        normalized_text = normalized_path.read_text(encoding="utf-8")
        blocks = block_mod.blockify(
            text=normalized_text,
            source_hash=file_hash,
            mineru_artifacts=mineru_artifacts,
            run_dir=str(run_dir),
        )
        with open(blocks_path, "w", encoding="utf-8") as f:
            for block in blocks:
                f.write(json.dumps(block, ensure_ascii=False) + "\n")
        _stderr_log("info", "blockify", f"Created {len(blocks)} blocks")
        # Stage 7: classify_blocks
        _stderr_log("info", "classify_blocks", "Classifying blocks")
        from . import classify_blocks as cls_mod
        blocks = cls_mod.classify_blocks(blocks)
        with open(blocks_path, "w", encoding="utf-8") as f:
            for block in blocks:
                f.write(json.dumps(block, ensure_ascii=False) + "\n")
        _stderr_log("info", "classify_blocks", "Classification complete")
        # Stage 8: clean_rules
        _stderr_log("info", "clean_rules", "Applying cleaning rules")
        from . import clean_rules as clean_mod
        blocks = clean_mod.apply_clean_rules(blocks)
        with open(blocks_path, "w", encoding="utf-8") as f:
            for block in blocks:
                f.write(json.dumps(block, ensure_ascii=False) + "\n")
        _stderr_log("info", "clean_rules", "Cleaning rules applied")
        # Stage 9: image_clean
        _stderr_log("info", "image_clean", "Classifying images")
        try:
            from . import images as img_mod
            blocks = img_mod.classify_images(blocks, str(run_dir))
            with open(blocks_path, "w", encoding="utf-8") as f:
                for block in blocks:
                    f.write(json.dumps(block, ensure_ascii=False) + "\n")
            _stderr_log("info", "image_clean", "Image classification complete")
        except Exception as e:
            _stderr_log("warn", "image_clean", str(e))
            warnings.append(f"Image classification failed: {e}")

        if mode == "rules_plus_review_pack":
            _stderr_log("info", "review_pack", "Generating review pack")
            _generate_review_pack(blocks, run_dir, source_type)
        # Stage 10: render_outputs
        _stderr_log("info", "render_outputs", "Rendering output files")
        from . import render_outputs as render_mod
        render_mod.render(
            blocks=blocks,
            run_dir=str(run_dir),
            source_hash=file_hash,
            run_id=run_id,
        )
        _stderr_log("info", "render_outputs", "Output files rendered")
        # Stage 11: split
        _stderr_log("info", "split", "Splitting into chunks")
        from . import split as split_mod
        splitter_type = override_splitter if override_splitter != "auto" else source_type
        split_result = split_mod.split_into_chunks(
            blocks=blocks,
            run_dir=str(run_dir),
            source_type=splitter_type,
            source_hash=file_hash,
            run_id=run_id,
            split_strategy=diagnosis.get("split_strategy"),
        )
        warnings.extend(split_result.get("warnings", []))
        _stderr_log("info", "split", f"Created {split_result.get('chunk_count', 0)} chunks")
        # Stage 12: quality_check
        _stderr_log("info", "quality_check", "Running quality checks")
        from . import quality as qa_mod
        quality_report = qa_mod.run_quality_check(
            blocks=blocks,
            run_dir=str(run_dir),
            source_type=source_type,
            diagnosis=diagnosis,
        )
        strict_errors.extend(quality_report.get("strict_errors", []))
        warnings.extend(quality_report.get("warnings", []))
        quality_report["source_sha256"] = file_hash
        quality_report["config_hash"] = config_hash
        quality_report["plugin_version"] = plugin_version
        quality_report["mineru_version"] = mineru_version
        quality_report["runtime_cache_key"] = runtime_cache_key
        quality_report["runtime"] = runtime
        (run_dir / "quality_report.json").write_text(
            json.dumps(quality_report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        _stderr_log("info", "quality_check", f"Quality: {len(strict_errors)} strict errors, {len(warnings)} warnings")

    except PipelineError as e:
        _stderr_log("error", "pipeline", e.message, e.code)
        details = dict(e.details)
        details.update(_write_error_report_from_context(locals(), e.code, e.message, warnings))
        fail(e.code, e.message, details=details, warnings=warnings)
        return
    except FileNotFoundError as e:
        _stderr_log("error", "pipeline", str(e), "E_MINERU_NOT_FOUND")
        details = _write_error_report_from_context(locals(), "E_MINERU_NOT_FOUND", str(e), warnings)
        fail("E_MINERU_NOT_FOUND", f"MinerU not found: {e}", details=details, warnings=warnings, recoverable=False,
             suggested_action="Rebuild the plugin-local .kbprep/venv so MinerU is installed there.")
        return
    except TimeoutError as e:
        _stderr_log("error", "pipeline", str(e), "E_TIMEOUT")
        details = _write_error_report_from_context(locals(), "E_TIMEOUT", str(e), warnings)
        details["mineru_timeout_seconds"] = _mineru_timeout_seconds_from_env()
        fail(
            "E_TIMEOUT",
            str(e),
            details=details,
            warnings=warnings,
            recoverable=True,
            suggested_action="Increase plugin config mineru_timeout_seconds, try a smaller sample first, or verify MinerU/GPU readiness with kbprep_preflight.",
        )
        return
    except Exception as e:
        error_code = "E_CONVERT_FAILED" if type(e).__name__ == "MinerUProcessError" else "KBPREP_INTERNAL"
        _stderr_log("error", "pipeline", str(e), error_code)
        import traceback
        tb = traceback.format_exc()
        _stderr_log("error", "pipeline", tb)
        details = {"exception_type": type(e).__name__}
        details.update(_write_error_report_from_context(locals(), error_code, str(e), warnings, traceback_text=tb))
        extra_details = getattr(e, "details", None)
        if isinstance(extra_details, dict):
            details.update(extra_details)
        fail(error_code, str(e), details=details, warnings=warnings)
        return
    # Generate audit.md
    try:
        audit_md = _generate_audit_md(
            input_name=input_p.name,
            file_hash=file_hash,
            plugin_version=plugin_version,
            mineru_version=mineru_version,
            python_version=python_version,
            runtime=runtime,
            diagnosis=diagnosis,
            blocks=blocks,
            quality_report=quality_report,
            warnings=warnings,
            strict_errors=strict_errors,
        )
        (run_dir / "audit.md").write_text(audit_md, encoding="utf-8")
    except Exception as e:
        _stderr_log("warn", "audit", f"Failed to generate audit.md: {e}")
    # Update latest.json
    latest_outputs = _latest_output_paths(root_p)
    if not strict_errors:
        latest_outputs = _publish_latest_outputs(run_dir, root_p)
        latest_file.write_text(json.dumps({
            "source_sha256": file_hash,
            "run_id": run_id,
            "source_type": source_type,
            "input_path": str(input_p),
            "run_dir": str(run_dir),
            "latest_outputs": latest_outputs,
            "timestamp": time.time(),
            "plugin_version": plugin_version,
            "mineru_version": mineru_version,
            "runtime_cache_key": runtime_cache_key,
            "runtime": runtime,
        }, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        _stderr_log("warn", "quality_check", "Strict errors: latest.json NOT updated")
    # Final output
    chunks_dir = run_dir / "chunks"
    chunk_count = len(list(chunks_dir.glob("*.md"))) if chunks_dir.exists() else 0

    ok(data={
        "ok": True,
        "run_id": run_id,
        "run_dir": str(run_dir),
        "latest_outputs": latest_outputs,
        "outputs": {
            "converted_md": str(run_dir / "converted.md"),
            "normalized_md": str(run_dir / "normalized.md"),
            "diagnosis_report": str(run_dir / "diagnosis_report.json"),
            "blocks_jsonl": str(run_dir / "blocks.jsonl"),
            "cleaned_md": str(run_dir / "cleaned.md"),
            "discarded_md": str(run_dir / "discarded.md"),
            "review_needed_md": str(run_dir / "review_needed.md"),
            "audit_md": str(run_dir / "audit.md"),
            "quality_report": str(run_dir / "quality_report.json"),
            "chunks_dir": str(chunks_dir),
            "parts_dir": str(run_dir / "parts"),
            "review_pack": str(run_dir / "review_pack.json") if (run_dir / "review_pack.json").exists() else None,
        },
        "chunk_count": chunk_count,
        "warnings": warnings,
        "strict_errors": strict_errors,
    }, warnings=warnings)


def _latest_output_paths(root_p: Path) -> dict:
    """Return stable top-level paths for the latest successful run."""
    return {
        "converted_md": str(root_p / "converted.md"),
        "diagnosis_report": str(root_p / "diagnosis_report.json"),
        "blocks_jsonl": str(root_p / "blocks.jsonl"),
        "cleaned_md": str(root_p / "cleaned.md"),
        "discarded_md": str(root_p / "discarded.md"),
        "review_needed_md": str(root_p / "review_needed.md"),
        "quality_report": str(root_p / "quality_report.json"),
        "conversion_report": str(root_p / "conversion_report.json"),
        "audit_md": str(root_p / "audit.md"),
        "parts_dir": str(root_p / "parts"),
        "review_pack": str(root_p / "review_pack.json"),
    }


def _write_diagnosis_report(
    run_dir: Path,
    input_path: Path,
    file_hash: str,
    source_type: str,
    diagnosis: dict,
    runtime: dict,
    warnings: list[str],
) -> None:
    fallback = _diagnosis_fallback(input_path)
    report = {
        "schema": "kbprep.diagnosis_report.v1",
        "input_file": input_path.name,
        "input_extension": input_path.suffix.lower(),
        "source_sha256": file_hash,
        "source_type": source_type,
        "detected_format": diagnosis.get("detected_format") or fallback["detected_format"],
        "recommended_pipeline": diagnosis.get("recommended_pipeline") or fallback["recommended_pipeline"],
        "conversion_strategy": diagnosis.get("conversion_strategy") or fallback["conversion_strategy"],
        "split_strategy": diagnosis.get("split_strategy"),
        "text_profile": diagnosis.get("text_profile"),
        "text_layer_health": diagnosis.get("text_layer_health"),
        "pdf_subtype": diagnosis.get("pdf_subtype"),
        "layout_profile": diagnosis.get("layout_profile"),
        "slide_like_score": diagnosis.get("slide_like_score"),
        "needs_ocr": diagnosis.get("needs_ocr"),
        "processing_hints": diagnosis.get("processing_hints", []),
        "runtime": runtime,
        "diagnosis": diagnosis,
        "warnings": warnings,
    }
    (run_dir / "diagnosis_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _diagnosis_fallback(input_path: Path) -> dict:
    ext = input_path.suffix.lower()
    detected_format = FORMAT_BY_EXTENSION.get(ext, "unknown")
    if ext in DIRECT_EXTENSIONS:
        strategy = "direct"
    elif ext in OFFICE_XML_EXTENSIONS:
        strategy = "office_xml"
    elif ext in EPUB_EXTENSIONS:
        strategy = "epub_xhtml"
    elif ext in MEDIA_EXTENSIONS:
        strategy = "provide_transcript_first"
    else:
        strategy = "mineru"
    return {
        "detected_format": detected_format,
        "recommended_pipeline": strategy,
        "conversion_strategy": strategy,
    }


def _write_error_report_from_context(
    context: dict,
    code: str,
    message: str,
    warnings: list[str],
    traceback_text: str | None = None,
) -> dict:
    """Persist failure evidence when a run directory already exists."""
    run_dir = context.get("run_dir")
    if not isinstance(run_dir, Path):
        return {}

    input_p = context.get("input_p")
    root_p = context.get("root_p")
    original_file = context.get("original_file")
    report = {
        "schema": "kbprep.error_report.v1",
        "code": code,
        "message": message,
        "input_path": str(input_p) if isinstance(input_p, Path) else None,
        "output_root": str(root_p) if isinstance(root_p, Path) else None,
        "run_dir": str(run_dir),
        "original_file": str(original_file) if isinstance(original_file, Path) and original_file.exists() else None,
        "source_sha256": context.get("file_hash", ""),
        "source_type": context.get("source_type", "unknown"),
        "plugin_version": context.get("plugin_version", "unknown"),
        "mineru_version": context.get("mineru_version", "unknown"),
        "runtime": context.get("runtime", {}),
        "diagnosis": context.get("diagnosis", {}),
        "warnings": warnings,
    }
    if traceback_text:
        report["traceback_tail"] = traceback_text.splitlines()[-40:]

    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        error_report = run_dir / "error_report.json"
        error_report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        return {
            "run_dir": str(run_dir),
            "original_file": report["original_file"],
            "error_report": str(error_report),
            "runtime": report["runtime"],
            "diagnosis": report["diagnosis"],
        }
    except Exception as report_error:
        return {
            "run_dir": str(run_dir),
            "error_report_error": str(report_error),
        }


def _publish_latest_outputs(run_dir: Path, root_p: Path) -> dict:
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

    src_parts = run_dir / "parts"
    dst_parts = root_p / "parts"
    if dst_parts.exists():
        shutil.rmtree(dst_parts)
    if src_parts.exists():
        shutil.copytree(src_parts, dst_parts)
    else:
        dst_parts.mkdir(parents=True, exist_ok=True)

    return _latest_output_paths(root_p)


def _check_env(profile: str) -> list[str]:
    warnings = []
    if sys.version_info < (3, 10):
        warnings.append("Python < 3.10 detected. Some features may not work.")
    import shutil as sh
    if not sh.which("uv"):
        warnings.append("uv not found. Venv management will fail.")
    return warnings


def _get_mineru_version() -> str:
    try:
        from .mineru_adapter import find_mineru
        mineru = find_mineru()
        r = subprocess.run([mineru, "--version"], capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            return r.stdout.strip().split()[-1]
    except Exception:
        pass
    return "unknown"


def _runtime_snapshot(mineru_version: str) -> dict:
    runtime = {
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "python_executable": sys.executable,
        "mineru_version": mineru_version,
        "mineru_path": None,
        "torch": "not installed",
        "torch_cuda_available": False,
        "torch_cuda_version": "not installed",
        "torch_device_count": 0,
        "mineru_device": "unknown",
    }
    try:
        from .mineru_adapter import find_mineru
        runtime["mineru_path"] = find_mineru()
    except Exception:
        pass
    try:
        import torch
        runtime["torch"] = str(torch.__version__)
        runtime["torch_cuda_available"] = bool(torch.cuda.is_available())
        runtime["torch_cuda_version"] = torch.version.cuda or "none"
        runtime["torch_device_count"] = int(torch.cuda.device_count())
        if torch.cuda.is_available():
            runtime["gpu_name"] = torch.cuda.get_device_name(0)
    except Exception:
        pass
    try:
        from .setup_env import detect_device
        runtime["mineru_device"] = detect_device()
    except Exception:
        pass
    return runtime


def _runtime_cache_key(runtime: dict) -> str:
    """Build a stable cache key for outputs that can change with runtime selection."""
    identity = {
        "python_executable": runtime.get("python_executable"),
        "mineru_path": runtime.get("mineru_path"),
        "mineru_version": runtime.get("mineru_version"),
        "torch": runtime.get("torch"),
        "torch_cuda_available": runtime.get("torch_cuda_available"),
        "torch_cuda_version": runtime.get("torch_cuda_version"),
        "mineru_device": runtime.get("mineru_device"),
    }
    payload = json.dumps(identity, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _mineru_timeout_seconds_from_env() -> int | None:
    raw = os.environ.get("KBPREP_MINERU_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return None
    try:
        return int(float(raw))
    except ValueError:
        return None


def _validate_convertible_container(input_p: Path) -> None:
    """Fail fast for modern Office-like containers before invoking heavy converters."""
    zip_container_exts = {".docx", ".pptx", ".xlsx", ".epub", ".odt", ".odp", ".ods"}
    if input_p.suffix.lower() in zip_container_exts and not zipfile.is_zipfile(input_p):
        raise PipelineError(
            "E_CONVERT_INPUT_INVALID",
            f"{input_p.name} is not a valid Office ZIP container. Check whether the file is corrupted or mislabeled.",
            {"extension": input_p.suffix.lower()},
        )


def _run_mineru_conversion(
    input_p: Path,
    converted_path: Path,
    run_dir: Path,
    language: str,
    mode: str,
) -> dict:
    _validate_convertible_container(input_p)
    from . import mineru_adapter

    result = mineru_adapter.run_mineru(
        input_path=str(input_p),
        output_dir=str(run_dir),
        language=language,
        mode=mode,
        keep_debug_files=False,
    )
    source_md = Path(result["source_md_path"])
    if not source_md.exists():
        raise PipelineError(
            "E_CONVERT_OUTPUT_MISSING",
            f"MinerU did not produce source Markdown: {source_md}",
            {"source_md_path": str(source_md)},
        )
    shutil.copy2(str(source_md), str(converted_path))
    return result


def _maybe_fallback_pdf_text_layer_to_mineru(
    input_p: Path,
    converted_path: Path,
    run_dir: Path,
    language: str,
    text_layer_artifacts: dict,
) -> dict | None:
    text = converted_path.read_text(encoding="utf-8") if converted_path.exists() else ""
    quality = _converted_text_quality(text)
    text_layer_artifacts["post_convert_text_quality"] = quality

    if not _pdf_text_layer_output_needs_ocr(quality):
        return None

    rejected_path = run_dir / "converted.pdf_text_layer.rejected.md"
    if converted_path.exists():
        shutil.copy2(str(converted_path), str(rejected_path))

    fallback = _run_mineru_conversion(
        input_p=input_p,
        converted_path=converted_path,
        run_dir=run_dir,
        language=language,
        mode="ocr",
    )
    fallback["fallback_from"] = "pdf_text_layer"
    fallback["fallback_reason"] = "post_convert_text_unreadable"
    fallback["rejected_text_layer_md"] = str(rejected_path)
    fallback["post_convert_text_quality"] = quality
    fallback["warnings"] = [
        *fallback.get("warnings", []),
        (
            "W_PDF_TEXT_LAYER_FALLBACK_TO_OCR: text-layer conversion produced unreadable Markdown "
            f"(unreadable={quality.get('unreadable_text_ratio', 0):.2%}, "
            f"garbled={quality.get('garbled_ratio', 0):.2%}); reran MinerU in OCR mode."
        ),
    ]
    return fallback


def _converted_text_quality(text: str) -> dict:
    from .diagnose import analyze_text_quality
    return analyze_text_quality(text)


def _pdf_text_layer_output_needs_ocr(quality: dict) -> bool:
    return (
        quality.get("total_chars", 0) > 0
        and (
            quality.get("unreadable_text_ratio", 0) > 0.08
            or quality.get("garbled_ratio", 0) > 0.08
            or quality.get("mojibake_ratio", 0) > 0.08
            or quality.get("replacement_char_ratio", 0) > 0.08
        )
    )


def _office_xml_to_markdown(input_p: Path) -> tuple[str, list[str]]:
    """Extract readable Markdown from modern Office Open XML files without heavy converters."""
    ext = input_p.suffix.lower()
    warnings: list[str] = []
    try:
        with zipfile.ZipFile(input_p) as zf:
            if ext == ".docx":
                markdown = _docx_to_markdown(zf)
            elif ext == ".pptx":
                markdown = _pptx_to_markdown(zf)
            elif ext == ".xlsx":
                markdown = _xlsx_to_markdown(zf)
            else:
                raise ValueError(f"Unsupported Office XML extension: {ext}")
    except KeyError as e:
        raise PipelineError(
            "E_CONVERT_INPUT_INVALID",
            f"{input_p.name} is missing required Office XML part: {e}",
            {"extension": ext},
        )
    except zipfile.BadZipFile:
        raise PipelineError(
            "E_CONVERT_INPUT_INVALID",
            f"{input_p.name} is not a valid Office ZIP container. Check whether the file is corrupted or mislabeled.",
            {"extension": ext},
        )

    if not markdown.strip():
        raise PipelineError(
            "E_CONVERT_OUTPUT_EMPTY",
            f"{input_p.name} did not contain extractable Office text.",
            {"extension": ext},
        )

    warnings.append("W_OFFICE_XML_CONVERTER_USED: extracted text directly from Office XML; complex layout fidelity may be limited.")
    return markdown.strip() + "\n", warnings


def _docx_to_markdown(zf: zipfile.ZipFile) -> str:
    import xml.etree.ElementTree as ET

    root = ET.fromstring(zf.read("word/document.xml"))
    body = _first_child_by_local_name(root, "body")
    if body is None:
        return ""

    lines: list[str] = []
    for child in list(body):
        local = _local_name(child.tag)
        if local == "p":
            text = _xml_text(child)
            if text:
                heading = _docx_heading_level(child)
                lines.append(("#" * heading + " " + text) if heading else text)
        elif local == "tbl":
            table = _word_table_to_markdown(child)
            if table:
                lines.append(table)
    return "\n\n".join(lines)


def _pptx_to_markdown(zf: zipfile.ZipFile) -> str:
    import re
    import xml.etree.ElementTree as ET

    slide_names = sorted(
        (name for name in zf.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)),
        key=lambda name: int(re.search(r"slide(\d+)\.xml", name).group(1)),
    )
    sections: list[str] = []
    for idx, name in enumerate(slide_names, start=1):
        root = ET.fromstring(zf.read(name))
        paragraphs = _drawing_paragraphs(root)
        if paragraphs:
            title = paragraphs[0]
            body = paragraphs[1:]
            section_lines = [f"# Slide {idx}: {title}"] if title else [f"# Slide {idx}"]
            section_lines.extend(body)
            sections.append("\n\n".join(section_lines))

        notes_name = f"ppt/notesSlides/notesSlide{idx}.xml"
        if notes_name in zf.namelist():
            notes_root = ET.fromstring(zf.read(notes_name))
            notes = _drawing_paragraphs(notes_root)
            if notes:
                sections.append("\n\n".join([f"## Slide {idx} Notes", *notes]))
    return "\n\n".join(sections)


def _xlsx_to_markdown(zf: zipfile.ZipFile) -> str:
    import re
    import xml.etree.ElementTree as ET

    shared_strings = _xlsx_shared_strings(zf)
    sheet_names = _xlsx_sheet_names(zf)
    worksheet_names = sorted(
        (name for name in zf.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name)),
        key=lambda name: int(re.search(r"sheet(\d+)\.xml", name).group(1)),
    )

    sections: list[str] = []
    for idx, name in enumerate(worksheet_names, start=1):
        root = ET.fromstring(zf.read(name))
        rows: list[list[str]] = []
        for row_el in _iter_by_local_name(root, "row"):
            values: list[str] = []
            for cell in [c for c in list(row_el) if _local_name(c.tag) == "c"]:
                values.append(_xlsx_cell_value(cell, shared_strings))
            if any(value.strip() for value in values):
                rows.append(values)
        if rows:
            title = sheet_names[idx - 1] if idx - 1 < len(sheet_names) else f"Sheet {idx}"
            sections.append("\n\n".join([f"# {title}", _rows_to_markdown_table(rows)]))
    return "\n\n".join(sections)


def _docx_heading_level(p_el) -> int:
    for node in p_el.iter():
        if _local_name(node.tag) == "pStyle":
            value = _xml_attr_by_local_name(node, "val")
            if not value:
                continue
            lowered = value.lower()
            if lowered.startswith("heading"):
                digits = "".join(ch for ch in lowered if ch.isdigit())
                if digits:
                    return max(1, min(6, int(digits)))
            if lowered in {"title", "subtitle"}:
                return 1
    return 0


def _word_table_to_markdown(tbl_el) -> str:
    rows: list[list[str]] = []
    for tr in [n for n in tbl_el.iter() if _local_name(n.tag) == "tr"]:
        cells = [_xml_text(tc) for tc in list(tr) if _local_name(tc.tag) == "tc"]
        if any(cell.strip() for cell in cells):
            rows.append(cells)
    return _rows_to_markdown_table(rows)


def _drawing_paragraphs(root) -> list[str]:
    paragraphs: list[str] = []
    for p in _iter_by_local_name(root, "p"):
        text = _xml_text(p)
        if text and text not in paragraphs:
            paragraphs.append(text)
    return paragraphs


def _xlsx_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    import xml.etree.ElementTree as ET

    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    return [_xml_text(si) for si in _iter_by_local_name(root, "si")]


def _xlsx_sheet_names(zf: zipfile.ZipFile) -> list[str]:
    import xml.etree.ElementTree as ET

    if "xl/workbook.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/workbook.xml"))
    names: list[str] = []
    for sheet in _iter_by_local_name(root, "sheet"):
        name = _xml_attr_by_local_name(sheet, "name")
        if name:
            names.append(name)
    return names


def _xlsx_cell_value(cell, shared_strings: list[str]) -> str:
    cell_type = _xml_attr_by_local_name(cell, "t")
    value_node = _first_child_by_local_name(cell, "v")
    if cell_type == "inlineStr":
        return _xml_text(cell)
    if value_node is None or value_node.text is None:
        return ""
    raw = value_node.text.strip()
    if cell_type == "s":
        try:
            return shared_strings[int(raw)]
        except (ValueError, IndexError):
            return raw
    return raw


def _rows_to_markdown_table(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    max_cols = max(len(row) for row in rows)
    padded = [row + [""] * (max_cols - len(row)) for row in rows]
    header = padded[0]
    body = padded[1:]
    lines = [
        "| " + " | ".join(_escape_table_cell(cell) for cell in header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for row in body:
        lines.append("| " + " | ".join(_escape_table_cell(cell) for cell in row) + " |")
    return "\n".join(lines)


def _xml_text(element) -> str:
    parts: list[str] = []
    for node in element.iter():
        local = _local_name(node.tag)
        if local == "t" and node.text:
            parts.append(node.text)
        elif local in {"tab"}:
            parts.append("\t")
        elif local in {"br", "cr"}:
            parts.append("\n")
    text = "".join(parts)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _iter_by_local_name(element, local_name: str):
    for node in element.iter():
        if _local_name(node.tag) == local_name:
            yield node


def _first_child_by_local_name(element, local_name: str):
    for child in list(element):
        if _local_name(child.tag) == local_name:
            return child
    return None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _xml_attr_by_local_name(element, local_name: str) -> str | None:
    for key, value in element.attrib.items():
        if _local_name(key) == local_name:
            return value
    return None


def _read_with_fallback(path: Path) -> str:
    for enc in ["utf-8", "utf-8-sig", "gbk", "gb2312", "latin-1"]:
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, LookupError):
            continue
    raise ValueError(f"Cannot decode {path.name}")


def _read_direct_source(path: Path) -> str:
    text = _read_with_fallback(path)
    ext = path.suffix.lower()
    if ext in {".vtt", ".srt", ".ass", ".lrc"}:
        return _normalize_subtitle_transcript(text)
    if ext in {".html", ".htm"}:
        return _html_to_markdown(text)
    if ext == ".json":
        return _json_to_markdown(text)
    if ext in NOTEBOOK_EXTENSIONS:
        from .notebook import notebook_to_markdown
        return notebook_to_markdown(path)
    if ext in {".csv", ".tsv"}:
        return _delimited_to_markdown(text, delimiter="\t" if ext == ".tsv" else ",")
    if ext in CODE_EXTENSIONS:
        return _code_to_markdown(text, ext)
    return text


def _code_to_markdown(text: str, ext: str) -> str:
    lang = CODE_LANGUAGE_BY_EXTENSION.get(ext, "")
    body = text.rstrip()
    fence = "```"
    while fence in body:
        fence += "`"
    return f"{fence}{lang}\n{body}\n{fence}\n"


class _HTMLToMarkdownParser(HTMLParser):
    """Small stdlib HTML reader for saved pages and exported web notes."""

    BLOCK_TAGS = {"article", "main", "section", "p", "div", "blockquote", "tr"}
    SKIP_TAGS = {"script", "style", "svg", "noscript", "nav", "header", "footer"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lines: list[str] = []
        self.current: list[str] = []
        self.skip_depth = 0
        self.heading_level: int | None = None
        self.in_li = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._flush()
            self.heading_level = int(tag[1])
        elif tag == "li":
            self._flush()
            self.in_li = True
        elif tag == "br":
            self._flush()
        elif tag in self.BLOCK_TAGS:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1
            return
        if self.skip_depth:
            return
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._flush(heading_level=self.heading_level)
            self.heading_level = None
        elif tag == "li":
            self._flush(list_item=True)
            self.in_li = False
        elif tag in self.BLOCK_TAGS or tag in {"ul", "ol", "table"}:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        text = re.sub(r"\s+", " ", data).strip()
        if text:
            self.current.append(text)

    def _flush(self, heading_level: int | None = None, list_item: bool = False) -> None:
        text = " ".join(self.current).strip()
        self.current = []
        if not text:
            return
        if heading_level:
            self.lines.append(f"{'#' * min(heading_level, 6)} {text}")
        elif list_item:
            self.lines.append(f"- {text}")
        else:
            self.lines.append(text)

    def markdown(self) -> str:
        self._flush(heading_level=self.heading_level, list_item=self.in_li)
        cleaned: list[str] = []
        previous = ""
        for line in self.lines:
            line = line.strip()
            if line and line != previous:
                cleaned.append(line)
                previous = line
        return "\n\n".join(cleaned).strip() + "\n"


def _html_to_markdown(text: str) -> str:
    parser = _HTMLToMarkdownParser()
    parser.feed(text)
    markdown = parser.markdown()
    return markdown if markdown.strip() else re.sub(r"<[^>]+>", "", text).strip() + "\n"


def _json_to_markdown(text: str) -> str:
    try:
        parsed = json.loads(text)
        pretty = json.dumps(parsed, indent=2, ensure_ascii=False)
    except json.JSONDecodeError:
        pretty = text.strip()
    return "```json\n" + pretty + "\n```\n"


def _delimited_to_markdown(text: str, delimiter: str) -> str:
    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    rows = [[cell.strip() for cell in row] for row in rows if any(cell.strip() for cell in row)]
    if not rows:
        return ""
    max_cols = max(len(row) for row in rows)
    rows = [row + [""] * (max_cols - len(row)) for row in rows]
    header = rows[0]
    body = rows[1:]
    lines = [
        "| " + " | ".join(_escape_table_cell(cell) for cell in header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for row in body:
        lines.append("| " + " | ".join(_escape_table_cell(cell) for cell in row) + " |")
    return "\n".join(lines) + "\n"


def _escape_table_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


def _normalize_subtitle_transcript(text: str) -> str:
    """Convert subtitle timing files into readable transcript markdown."""
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw.strip()
        if not line:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        if line.upper() == "WEBVTT":
            continue
        if line.isdigit():
            continue
        if "-->" in line:
            continue
        if line.startswith(("NOTE", "STYLE", "REGION")):
            continue
        # Strip common WebVTT cue tags but keep the spoken text.
        line = re.sub(r"<[^>]+>", "", line)
        line = re.sub(r"^\[[^\]]{1,30}\]\s*", "", line)
        if line:
            lines.append(line)

    paragraphs: list[str] = []
    current = ""
    for line in lines:
        if not line:
            if current:
                paragraphs.append(current.strip())
                current = ""
            continue
        candidate = f"{current} {line}".strip() if current else line
        if len(candidate) > 500:
            if current:
                paragraphs.append(current.strip())
            current = line
        else:
            current = candidate
    if current:
        paragraphs.append(current.strip())

    return "# Transcript\n\n" + "\n\n".join(paragraphs) + "\n"


def _write_conversion_report(
    run_dir: Path,
    input_path: Path,
    output_path: Path,
    converter: str,
    source_type: str,
    mineru_artifacts: dict,
    runtime: dict,
    diagnosis: dict,
    warnings: list[str],
) -> None:
    report = {
        "input_file": input_path.name,
        "input_extension": input_path.suffix.lower(),
        "converter": converter,
        "source_type": source_type,
        "diagnosed_format": diagnosis.get("detected_format"),
        "diagnosed_pipeline": diagnosis.get("recommended_pipeline"),
        "diagnosed_strategy": diagnosis.get("conversion_strategy"),
        "diagnosed_split_strategy": diagnosis.get("split_strategy"),
        "text_profile": diagnosis.get("text_profile"),
        "text_layer_health": diagnosis.get("text_layer_health"),
        "pdf_subtype": diagnosis.get("pdf_subtype"),
        "layout_profile": diagnosis.get("layout_profile"),
        "converted_md": str(output_path),
        "converted_bytes": output_path.stat().st_size if output_path.exists() else 0,
        "mineru_artifacts": mineru_artifacts,
        "runtime": runtime,
        "warnings": warnings,
    }
    (run_dir / "conversion_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _run_diagnose_subprocess(input_path: str, output_root: str, source_type: str) -> dict:
    payload = {
        "input_path": input_path,
        "output_root": output_root,
        "source_type": source_type,
    }
    proc = subprocess.run(
        [sys.executable, "-m", "kbprep_worker.cli", "diagnose", "--json-stdin"],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        cwd=str(Path(__file__).resolve().parents[1]),
        timeout=120,
    )
    stdout = proc.stdout.strip()
    if not stdout:
        return {
            "ok": False,
            "error": {
                "message": "diagnose subprocess returned empty stdout",
                "stderr_tail": proc.stderr.splitlines()[-20:],
            },
        }
    return json.loads(stdout.splitlines()[-1])


def _generate_review_pack(blocks: list[dict], run_dir: Path, source_type: str) -> None:
    candidates = []
    for block in blocks:
        status = block.get("status")
        risk_tags = block.get("risk_tags", [])
        confidence = float(block.get("confidence") or 0)
        if status == "review" or risk_tags or confidence < 0.76:
            candidates.append({
                "block_id": block.get("block_id"),
                "type": block.get("type"),
                "status": status,
                "risk_tags": risk_tags,
                "reason": block.get("reason", ""),
                "confidence": confidence,
                "protected": bool(block.get("protected")),
                "heading_path": block.get("heading_path", []),
                "page_range": [block.get("page_start"), block.get("page_end")],
                "text": block.get("text", ""),
                "allowed_patch_fields": ["status", "risk_tags", "reason", "confidence"],
            })

    pack = {
        "schema": "kbprep.review_pack.v1",
        "source_type": source_type,
        "instructions": [
            "Classify blocks only; never rewrite text.",
            "Prefer keep or review when a block may contain usable knowledge.",
            "Never discard steps, prompts, code, tables, tool names, numbers, parameters, links, or concrete examples.",
            "Return RFC 6902 JSON Patch operations against /blocks/<block_id>/<field>.",
        ],
        "blocks": candidates,
    }
    (run_dir / "review_pack.json").write_text(
        json.dumps(pack, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _find_existing_run(root_p: Path, file_hash: str, config_hash: str, plugin_version: str, runtime_cache_key: str) -> dict | None:
    runs_dir = root_p / "runs"
    if not runs_dir.exists():
        return None
    for run_dir in sorted(runs_dir.iterdir(), reverse=True):
        if not run_dir.is_dir():
            continue
        quality_file = run_dir / "quality_report.json"
        if quality_file.exists():
            try:
                report = json.loads(quality_file.read_text(encoding="utf-8"))
                if (report.get("source_sha256") == file_hash and
                    report.get("config_hash") == config_hash and
                    report.get("plugin_version") == plugin_version and
                    report.get("runtime_cache_key") == runtime_cache_key):
                    return {"run_id": run_dir.name, "run_dir": str(run_dir)}
            except Exception:
                continue
    return None


def _generate_audit_md(
    input_name: str,
    file_hash: str,
    plugin_version: str,
    mineru_version: str,
    python_version: str,
    runtime: dict,
    diagnosis: dict,
    blocks: list[dict],
    quality_report: dict,
    warnings: list[str],
    strict_errors: list[str],
) -> str:
    lines = [
        "# kbprep audit",
        "",
        "## Input",
        f"Filename: {input_name}",
        f"SHA256: {file_hash}",
        f"Plugin version: {plugin_version}",
        f"MinerU version: {mineru_version}",
        f"Python version: {python_version}",
        f"Python executable: {runtime.get('python_executable', 'unknown')}",
        f"MinerU path: {runtime.get('mineru_path', 'unknown')}",
        f"Torch: {runtime.get('torch', 'unknown')}",
        f"CUDA available: {runtime.get('torch_cuda_available', 'unknown')}",
        f"CUDA version: {runtime.get('torch_cuda_version', 'unknown')}",
        f"MinerU device: {runtime.get('mineru_device', 'unknown')}",
        "",
        "## Diagnosis",
        f"Format: {diagnosis.get('detected_format', 'unknown')}",
        f"Text layer health: {diagnosis.get('text_layer_health', 'unknown')}",
        f"Garbled ratio: {diagnosis.get('text_quality', {}).get('garbled_ratio', 'N/A')}",
        f"Needs OCR: {diagnosis.get('needs_ocr', 'unknown')}",
        "",
    ]

    status_counts = {}
    for b in blocks:
        s = b.get("status", "unclassified")
        status_counts[s] = status_counts.get(s, 0) + 1

    lines.append("## Block Statistics")
    for status, count in sorted(status_counts.items()):
        lines.append(f"- {status}: {count}")
    lines.append("")

    discard_blocks = [b for b in blocks if b.get("status") == "discard"]
    if discard_blocks:
        lines.append("## Deleted Content")
        for b in discard_blocks[:50]:
            bid = b.get("block_id", "?")
            btype = b.get("type", "unknown")
            reason = b.get("reason", "")
            lines.append(f"- {bid}: {btype}, reason: {reason}")
        if len(discard_blocks) > 50:
            lines.append(f"- ... and {len(discard_blocks) - 50} more")
        lines.append("")

    evidence_blocks = [b for b in blocks if b.get("status") == "evidence"]
    if evidence_blocks:
        lines.append("## Evidence")
        for b in evidence_blocks[:30]:
            bid = b.get("block_id", "?")
            btype = b.get("type", "unknown")
            lines.append(f"- {bid}: {btype}")
        lines.append("")

    risk_blocks = [b for b in blocks if b.get("status") == "keep" and b.get("risk_tags")]
    if risk_blocks:
        lines.append("## High-Risk Kept Content")
        for b in risk_blocks[:30]:
            bid = b.get("block_id", "?")
            tags = ", ".join(b.get("risk_tags", []))
            reason = b.get("reason", "")
            lines.append(f"- {bid}: {tags}, reason: {reason}")
        lines.append("")

    review_blocks = [b for b in blocks if b.get("status") == "review"]
    if review_blocks:
        lines.append("## Needs Review")
        for b in review_blocks[:30]:
            bid = b.get("block_id", "?")
            btype = b.get("type", "unknown")
            reason = b.get("reason", "")
            lines.append(f"- {bid}: {btype}, reason: {reason}")
        lines.append("")

    if warnings:
        lines.append("## Warnings")
        for w in warnings:
            lines.append(f"- {w}")
        lines.append("")

    if strict_errors:
        lines.append("## Strict Errors")
        for e in strict_errors:
            lines.append(f"- {e}")
        lines.append("")

    return "\n".join(lines)

