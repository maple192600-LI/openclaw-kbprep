"""
prepare - single-file pipeline.

Pipeline: env_check -> original_preserve -> diagnose -> convert -> normalize
-> blockify -> classify_blocks -> clean_rules -> image_clean
-> render intermediate outputs -> split -> quality_check -> export after pass

Each stage failure is tracked. If any stage fails, subsequent stages are skipped.
"""
import hashlib
import json
import logging
import re
import shutil
import sys
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from .. import __version__
from ..audit import AuditContext, generate_audit_md as _generate_audit_from_context
from ..envelope import ok, fail
from ..prepare_artifacts import (
    apply_artifact_policy as _apply_artifact_policy,
    latest_output_paths as _latest_output_paths,
    publish_latest_outputs as _publish_latest_outputs,
)
from ..prepare_errors import write_error_report_from_context as _write_error_report_from_context
from ..prepare_diagnosis import (
    source_title_for_render as _source_title_for_render,
    write_diagnosis_report as _write_diagnosis_report,
)
from ..prepare_runtime import (
    check_env as _check_env,
    get_mineru_version as _get_mineru_version,
    mineru_timeout_seconds_from_env as _mineru_timeout_seconds_from_env,
    runtime_cache_key as _runtime_cache_key,
    runtime_snapshot as _runtime_snapshot,
)
from ..converter_capabilities import get_capability_for_extension
from ..converters.direct import read_direct_source as _read_direct_source_impl
from ..converters.html import html_to_markdown as _html_to_markdown
from ..converters.office_xml import (
    OfficeXmlConversionError,
    office_xml_to_markdown as _office_xml_to_markdown,
    write_pptx_content_list as _write_pptx_content_list,
)
from ..quality.thresholds import DIAGNOSIS_THRESHOLDS
from ..supported_formats import (
    CODE_EXTENSIONS,
    DIRECT_EXTENSIONS,
    EPUB_EXTENSIONS,
    EXTERNAL_CONVERSION_REQUIRED_EXTENSIONS,
    IMAGE_EXTENSIONS,
    MARKDOWN_EXTENSIONS,
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


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default



@dataclass
class PipelineState:
    data: dict[str, Any]
    input_path: str = field(init=False)
    output_root: str = field(init=False)
    profile: str = field(init=False)
    mode: str = field(init=False)
    force: bool = field(init=False)
    language: str = field(init=False)
    override_source_type: str = field(init=False)
    override_splitter: str = field(init=False)
    artifact_policy: str = field(init=False)
    max_quality_iterations: int = field(init=False)
    repair_loop: bool = field(init=False)
    repair_iteration: int = field(init=False)
    repair_artifacts: dict[str, Any] = field(default_factory=dict)
    repair_results: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    strict_errors: list[str] = field(default_factory=list)
    diagnosis: dict[str, Any] = field(default_factory=dict)
    mineru_artifacts: dict[str, Any] = field(default_factory=dict)
    blocks: list[dict[str, Any]] = field(default_factory=list)
    quality_report: dict[str, Any] = field(default_factory=dict)
    latest_outputs: dict[str, Any] = field(default_factory=dict)
    document_type: str = "unknown"
    document_type_detection: dict[str, Any] = field(default_factory=dict)
    file_hash: str = ""
    file_size: int = 0
    plugin_version: str = "unknown"
    mineru_version: str = "unknown"
    python_version: str = "unknown"
    runtime: dict[str, Any] = field(default_factory=dict)
    runtime_cache_key: str = ""
    source_type: str = "unknown"
    source_identity: dict[str, Any] = field(default_factory=dict)
    config_hash: str = ""
    run_id: str = ""
    input_p: Path = field(init=False)
    root_p: Path = field(init=False)
    original_dir: Path | None = None
    runs_dir: Path | None = None
    run_dir: Path | None = None
    latest_file: Path | None = None
    original_file: Path | None = None
    converted_path: Path | None = None
    normalized_path: Path | None = None
    blocks_path: Path | None = None

    def __post_init__(self) -> None:
        self.input_path = self.data["input_path"]
        self.output_root = self.data.get("output_root", ".")
        self.profile = self.data.get("profile", "standard")
        self.mode = self.data.get("mode", "rules_only")
        self.force = self.data.get("force", False)
        self.language = self.data.get("language", "zh")
        self.override_source_type = self.data.get("source_type", "auto")
        self.override_splitter = self.data.get("splitter", "auto")
        self.artifact_policy = self.data.get("artifact_policy", "keep_latest")
        self.max_quality_iterations = _positive_int(self.data.get("max_quality_iterations"), 3)
        self.repair_loop = bool(self.data.get("repair_loop", False))
        self.repair_iteration = _positive_int(self.data.get("repair_loop_iteration"), 1)
        self.input_p = Path(self.input_path)
        self.root_p = Path(self.output_root)

    def error_context(self) -> dict[str, Any]:
        return {
            "run_dir": self.run_dir,
            "input_p": self.input_p,
            "root_p": self.root_p,
            "original_file": self.original_file,
            "file_hash": self.file_hash,
            "source_type": self.source_type,
            "plugin_version": self.plugin_version,
            "mineru_version": self.mineru_version,
            "runtime": self.runtime,
            "diagnosis": self.diagnosis,
        }


def run(data: dict) -> None:
    state = PipelineState(data)
    if not state.input_p.exists():
        fail("E_INPUT_NOT_FOUND", f"Input file does not exist: {state.input_path}")
        return

    try:
        _stage_env_check(state)
        if _stage_preserve_original(state):
            return
        _stage_diagnose(state)
        _stage_convert(state)
        _stage_normalize(state)
        _stage_blockify(state)
        _stage_classify_blocks(state)
        _stage_apply_cleaning_rules(state)
        _stage_image_and_obsidian_policy(state)
        _stage_review_pack(state)
        _stage_render_outputs(state)
        _stage_split(state)
        _stage_quality_check(state)
    except PipelineError as e:
        _handle_pipeline_error(state, e)
        return
    except FileNotFoundError as e:
        _handle_missing_mineru(state, e)
        return
    except TimeoutError as e:
        _handle_timeout(state, e)
        return
    except Exception as e:
        _handle_unexpected_error(state, e)
        return

    _stage_audit(state)
    _stage_publish_or_block(state)


def _stage_env_check(state: PipelineState) -> None:
    _stderr_log("info", "env_check", "Checking environment")
    state.warnings.extend(_check_env(state.profile))


def _stage_preserve_original(state: PipelineState) -> bool:
    _stderr_log("info", "original_preserve", "Computing file hash")
    file_bytes = state.input_p.read_bytes()
    state.file_hash = hashlib.sha256(file_bytes).hexdigest()
    state.file_size = len(file_bytes)
    state.plugin_version = __version__
    state.mineru_version = _get_mineru_version()
    state.python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    state.runtime = _runtime_snapshot(state.mineru_version)
    state.runtime_cache_key = _runtime_cache_key(state.runtime)

    from ..detect import detect_source_type
    state.source_type = state.override_source_type if state.override_source_type != "auto" else detect_source_type(state.input_path)
    state.source_identity = _source_identity_for_rules(state.input_p, state.data)
    config_str = json.dumps({
        "source_type": state.source_type,
        "language": state.language,
        "mode": state.mode,
        "splitter": state.override_splitter,
        "profile": state.profile,
        "artifact_policy": state.artifact_policy,
        "source_identity": state.source_identity,
    }, sort_keys=True)
    state.config_hash = hashlib.sha256(config_str.encode()).hexdigest()[:16]
    run_hash_input = f"{state.file_hash}:{state.config_hash}:{state.plugin_version}:{state.runtime_cache_key}"
    run_hash = hashlib.sha256(run_hash_input.encode()).hexdigest()
    state.run_id = f"{time.strftime('%Y%m%d_%H%M%S')}_{run_hash[:12]}"

    state.original_dir = state.root_p / "original"
    state.runs_dir = state.root_p / "runs"
    state.run_dir = state.runs_dir / state.run_id
    state.latest_file = state.root_p / "latest.json"

    if not state.force:
        existing = _find_existing_run(
            state.root_p, state.file_hash, state.config_hash, state.plugin_version, state.runtime_cache_key,
        )
        if existing:
            _stderr_log("info", "original_preserve", f"Skipping: matching run {existing['run_id']}")
            latest_outputs = _publish_latest_outputs(Path(existing["run_dir"]), state.root_p, state.input_p, state.profile)
            ok(data={
                "ok": True,
                "run_id": existing["run_id"],
                "run_dir": existing["run_dir"],
                "latest_outputs": latest_outputs,
                "skipped": True,
                "warnings": ["Already processed with same config. Use force=true to re-process."],
                "strict_errors": [],
            })
            return True

    state.original_dir.mkdir(parents=True, exist_ok=True)
    state.run_dir.mkdir(parents=True, exist_ok=True)
    (state.run_dir / "evidence").mkdir(exist_ok=True)
    (state.run_dir / "chunks").mkdir(exist_ok=True)
    (state.run_dir / "logs").mkdir(exist_ok=True)
    _write_run_metadata(
        run_dir=state.run_dir,
        run_id=state.run_id,
        input_path=state.input_p,
        output_root=state.root_p,
        source_type=state.source_type,
        language=state.language,
        mode=state.mode,
        splitter=state.override_splitter,
        profile=state.profile,
        artifact_policy=state.artifact_policy,
        force=state.force,
        file_hash=state.file_hash,
        file_size=state.file_size,
        config_hash=state.config_hash,
        plugin_version=state.plugin_version,
        mineru_version=state.mineru_version,
        runtime_cache_key=state.runtime_cache_key,
        runtime=state.runtime,
    )
    _update_run_metadata(state.run_dir, {"source_identity": state.source_identity})

    state.original_file = state.original_dir / f"{state.file_hash[:16]}{state.input_p.suffix}"
    if not state.original_file.exists():
        shutil.copy2(str(state.input_p), str(state.original_file))
        _stderr_log("info", "original_preserve", f"Original saved: {state.original_file.name}")
    return False


def _stage_diagnose(state: PipelineState) -> None:
    assert state.run_dir is not None
    _stderr_log("info", "diagnose", "Diagnosing file quality")
    try:
        diag_envelope = _run_diagnose_direct(state.input_path, state.output_root, state.override_source_type)
        if diag_envelope.get("ok"):
            state.diagnosis = diag_envelope.get("data", {})
            state.warnings.extend(state.diagnosis.get("warnings", []))
        else:
            state.warnings.append(f"Diagnosis failed: {diag_envelope.get('error', {}).get('message', 'unknown')}")
    except Exception as e:
        state.warnings.append(f"Diagnosis error: {e}")
        _stderr_log("warn", "diagnose", str(e))

    _write_diagnosis_report(
        run_dir=state.run_dir,
        input_path=state.input_p,
        file_hash=state.file_hash,
        source_type=state.source_type,
        diagnosis=state.diagnosis,
        runtime=state.runtime,
        warnings=state.warnings,
    )


def _stage_convert(state: PipelineState) -> None:
    assert state.run_dir is not None
    _stderr_log("info", "convert", "Converting file")
    state.converted_path = state.run_dir / "converted.md"
    ext = state.input_p.suffix.lower()

    if ext in EXTERNAL_CONVERSION_REQUIRED_EXTENSIONS:
        raise PipelineError(
            "E_UNSUPPORTED_TYPE",
            (
                f"{ext} is not supported by KBPrep's verified conversion routes. "
                "Convert it to PDF, DOCX, PPTX, XLSX, EPUB, Markdown, text, or a subtitle/transcript first."
            ),
            {
                "extension": ext,
                "recommended_pipeline": "external_conversion_required",
                "conversion_strategy": "unsupported_external_conversion_required",
            },
        )
    if ext in DIRECT_EXTENSIONS:
        text = _read_direct_source(state.input_p, run_dir=state.run_dir)
        if ext in MARKDOWN_EXTENSIONS:
            text, local_image_artifacts = _copy_local_markdown_image_assets(text, state.input_p, state.run_dir)
            state.mineru_artifacts.update(local_image_artifacts)
            state.warnings.extend(local_image_artifacts.get("warnings", []))
        state.converted_path.write_text(text, encoding="utf-8")
        _stderr_log("info", "convert", "Text-like file normalized directly")
    elif ext in OFFICE_XML_EXTENSIONS:
        _validate_convertible_container(state.input_p)
        try:
            text, office_warnings, office_artifacts = _office_xml_to_markdown(state.input_p, state.run_dir)
        except OfficeXmlConversionError as exc:
            raise PipelineError(exc.code, exc.message, exc.details) from exc
        state.converted_path.write_text(text, encoding="utf-8")
        state.mineru_artifacts.update(office_artifacts)
        if ext == ".pptx":
            state.mineru_artifacts.update(_write_pptx_content_list(text, state.run_dir))
            state.diagnosis["split_strategy"] = "preserve_slide_or_page_order"
        state.warnings.extend(office_warnings)
        _stderr_log("info", "convert", "Office XML converted directly")
    elif ext in EPUB_EXTENSIONS:
        _validate_convertible_container(state.input_p)
        from ..epub import convert_epub
        result, epub_warnings = convert_epub(state.input_p, state.converted_path, state.run_dir)
        state.mineru_artifacts = result
        state.warnings.extend(epub_warnings)
        _stderr_log("info", "convert", "EPUB XHTML converted directly")
    elif ext in MEDIA_EXTENSIONS:
        raise PipelineError(
            "E_UNSUPPORTED_TYPE",
            "Audio/video binaries are not transcribed in v1. Provide a local subtitle, transcript, or ASR text file.",
            {"extension": ext},
        )
    elif ext == ".pdf" and state.diagnosis.get("conversion_strategy") in {"pdf_text_layer", "pdf_text_layer_slide_order"}:
        from .. import pdf_text
        result = pdf_text.convert_text_layer_pdf(state.input_p, state.converted_path, state.run_dir)
        state.mineru_artifacts = result
        state.warnings.extend(result.get("warnings", []))
        _stderr_log("info", "convert", "PDF text layer converted directly")
        fallback = _maybe_fallback_pdf_text_layer_to_mineru(
            input_p=state.input_p,
            converted_path=state.converted_path,
            run_dir=state.run_dir,
            language=state.language,
            text_layer_artifacts=result,
        )
        if fallback:
            state.mineru_artifacts = fallback
            state.warnings.extend(fallback.get("warnings", []))
            _stderr_log("warn", "convert", "PDF text layer was unreadable; fell back to MinerU OCR")
    else:
        result = _run_mineru_conversion(state.input_p, state.converted_path, state.run_dir, state.language, "auto")
        state.mineru_artifacts = result
        state.warnings.extend(result.get("warnings", []))
        _stderr_log("info", "convert", "MinerU conversion complete")

    if not state.converted_path.exists():
        raise PipelineError("E_CONVERT_OUTPUT_MISSING", "converted.md not found after conversion")

    _stderr_log("info", "convert", f"Converted file size: {state.converted_path.stat().st_size} bytes")
    _write_conversion_report(
        run_dir=state.run_dir,
        input_path=state.input_p,
        output_path=state.converted_path,
        converter=(
            "direct_code" if ext in CODE_EXTENSIONS
            else "notebook_json" if ext in NOTEBOOK_EXTENSIONS
            else "direct_text" if ext in DIRECT_EXTENSIONS
            else "office_xml" if ext in OFFICE_XML_EXTENSIONS
            else "epub_xhtml" if state.mineru_artifacts.get("converter") == "epub_xhtml"
            else "mineru_after_pdf_text_layer_fallback" if state.mineru_artifacts.get("fallback_from") == "pdf_text_layer"
            else "pdf_text_layer" if state.mineru_artifacts.get("converter") == "pdf_text_layer"
            else "mineru"
        ),
        source_type=state.source_type,
        mineru_artifacts=state.mineru_artifacts,
        runtime=state.runtime,
        diagnosis=state.diagnosis,
        warnings=state.warnings,
    )


def _stage_normalize(state: PipelineState) -> None:
    assert state.run_dir is not None and state.converted_path is not None
    _stderr_log("info", "normalize", "Normalizing markdown")
    state.normalized_path = state.run_dir / "normalized.md"
    from .. import normalize as norm_mod
    norm_result = norm_mod.normalize(
        converted_text=state.converted_path.read_text(encoding="utf-8"),
        run_dir=str(state.run_dir),
        mineru_artifacts=state.mineru_artifacts,
    )
    state.normalized_path.write_text(norm_result["normalized_text"], encoding="utf-8")
    state.warnings.extend(norm_result.get("warnings", []))
    _stderr_log("info", "normalize", f"Normalized: {norm_result.get('fix_count', 0)} fixes applied")
    if not state.normalized_path.exists():
        raise PipelineError("E_NORMALIZE_FAILED", "normalized.md not found after normalization")


def _stage_blockify(state: PipelineState) -> None:
    assert state.run_dir is not None and state.normalized_path is not None
    _stderr_log("info", "blockify", "Building blocks")
    state.blocks_path = state.run_dir / "blocks.jsonl"
    from .. import blockify as block_mod
    normalized_text = state.normalized_path.read_text(encoding="utf-8")
    state.blocks = block_mod.blockify(
        text=normalized_text,
        source_hash=state.file_hash,
        mineru_artifacts=state.mineru_artifacts,
        run_dir=str(state.run_dir),
    )
    from ..document_type import classify_document_type as _classify_document_type
    state.document_type_detection = _classify_document_type(
        text=normalized_text,
        source_type=state.source_type,
        diagnosis={**state.diagnosis, "detected_format": state.diagnosis.get("detected_format")},
    )
    state.document_type = state.document_type_detection.get("document_type", "unknown")
    _update_run_metadata(state.run_dir, {
        "document_type": state.document_type,
        "document_type_detection": state.document_type_detection,
    })
    _stderr_log("info", "document_type", f"Document type: {state.document_type} ({state.document_type_detection.get('confidence', 0)})")
    _write_blocks(state.blocks_path, state.blocks)
    _stderr_log("info", "blockify", f"Created {len(state.blocks)} blocks")


def _stage_classify_blocks(state: PipelineState) -> None:
    assert state.blocks_path is not None
    _stderr_log("info", "classify_blocks", "Classifying blocks")
    from .. import classify_blocks as cls_mod
    state.blocks = cls_mod.classify_blocks(state.blocks, profile=state.profile, document_type=state.document_type)
    _write_blocks(state.blocks_path, state.blocks)
    _stderr_log("info", "classify_blocks", "Classification complete")


def _stage_apply_cleaning_rules(state: PipelineState) -> None:
    assert state.blocks_path is not None
    _stderr_log("info", "clean_rules", "Applying cleaning rules")
    from .. import clean_rules as clean_mod
    state.blocks = clean_mod.apply_clean_rules(
        state.blocks,
        profile=state.profile,
        document_type=state.document_type,
        source_identity=json.dumps(state.source_identity, ensure_ascii=False, sort_keys=True),
    )
    _write_blocks(state.blocks_path, state.blocks)
    _stderr_log("info", "clean_rules", "Cleaning rules applied")


def _stage_image_and_obsidian_policy(state: PipelineState) -> None:
    assert state.run_dir is not None and state.blocks_path is not None
    _stderr_log("info", "image_clean", "Classifying images")
    try:
        from .. import images as img_mod
        state.blocks = img_mod.classify_images(
            state.blocks, str(state.run_dir), profile=state.profile, document_type=state.document_type,
        )
        _write_blocks(state.blocks_path, state.blocks)
        _stderr_log("info", "image_clean", "Image classification complete")
    except Exception as e:
        _stderr_log("warn", "image_clean", str(e))
        state.warnings.append(f"Image classification failed: {e}")

    if state.profile in {"obsidian_kb", "curated_obsidian_kb"}:
        _stderr_log("info", state.profile, "Applying Obsidian knowledge-base policy")
        from .. import obsidian_kb as obsidian_mod
        state.blocks = obsidian_mod.apply_curated_obsidian_policy(
            state.blocks,
            template_name=obsidian_mod.template_for_profile(state.profile),
        )
        _write_blocks(state.blocks_path, state.blocks)
        _stderr_log("info", state.profile, "Obsidian policy applied")


def _stage_review_pack(state: PipelineState) -> None:
    assert state.run_dir is not None
    if state.mode == "rules_plus_review_pack":
        _stderr_log("info", "review_pack", "Generating review pack")
        _generate_review_pack(state.blocks, state.run_dir, state.source_type)


def _stage_render_outputs(state: PipelineState) -> None:
    assert state.run_dir is not None and state.converted_path is not None
    _stderr_log("info", "render_outputs", "Rendering output files")
    from .. import render_outputs as render_mod
    render_mod.render(
        blocks=state.blocks,
        run_dir=str(state.run_dir),
        source_hash=state.file_hash,
        run_id=state.run_id,
        profile=state.profile,
        source_title=_source_title_for_render(state.input_p, state.converted_path),
        render_obsidian=False,
    )
    _stderr_log("info", "render_outputs", "Output files rendered")


def _stage_split(state: PipelineState) -> None:
    assert state.run_dir is not None
    _stderr_log("info", "split", "Splitting into chunks")
    from .. import split as split_mod
    splitter_type = state.override_splitter if state.override_splitter != "auto" else state.source_type
    split_result = split_mod.split_into_chunks(
        blocks=state.blocks,
        run_dir=str(state.run_dir),
        source_type=splitter_type,
        source_hash=state.file_hash,
        run_id=state.run_id,
        split_strategy=state.diagnosis.get("split_strategy"),
    )
    state.warnings.extend(split_result.get("warnings", []))
    _stderr_log("info", "split", f"Created {split_result.get('chunk_count', 0)} chunks")


def _stage_quality_check(state: PipelineState) -> None:
    assert state.run_dir is not None
    _stderr_log("info", "quality_check", "Running quality checks")
    from .. import quality as qa_mod
    state.quality_report = qa_mod.run_quality_check(
        blocks=state.blocks,
        run_dir=str(state.run_dir),
        source_type=state.source_type,
        diagnosis=state.diagnosis,
        profile=state.profile,
        document_type=state.document_type,
        quality_iteration=state.repair_iteration,
        previous_quality_iteration=state.repair_iteration - 1 if state.repair_iteration > 1 else None,
        max_quality_iterations=state.max_quality_iterations,
    )
    state.strict_errors.extend(state.quality_report.get("strict_errors", []))
    state.warnings.extend(state.quality_report.get("warnings", []))
    state.quality_report.update({
        "source_sha256": state.file_hash,
        "config_hash": state.config_hash,
        "plugin_version": state.plugin_version,
        "mineru_version": state.mineru_version,
        "runtime_cache_key": state.runtime_cache_key,
        "runtime": state.runtime,
        "document_type_detection": state.document_type_detection,
    })
    (state.run_dir / "quality_report.json").write_text(
        json.dumps(state.quality_report, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    _stderr_log("info", "quality_check", f"Quality: {len(state.strict_errors)} strict errors, {len(state.warnings)} warnings")


def _stage_audit(state: PipelineState) -> None:
    assert state.run_dir is not None
    try:
        audit_md = _generate_audit_md(
            input_name=state.input_p.name,
            file_hash=state.file_hash,
            plugin_version=state.plugin_version,
            mineru_version=state.mineru_version,
            python_version=state.python_version,
            runtime=state.runtime,
            diagnosis=state.diagnosis,
            blocks=state.blocks,
            quality_report=state.quality_report,
            warnings=state.warnings,
            strict_errors=state.strict_errors,
        )
        (state.run_dir / "audit.md").write_text(audit_md, encoding="utf-8")
    except Exception as e:
        _stderr_log("warn", "audit", f"Failed to generate audit.md: {e}")


def _stage_publish_or_block(state: PipelineState) -> None:
    assert state.run_dir is not None and state.converted_path is not None and state.latest_file is not None
    state.latest_outputs = _latest_output_paths(state.root_p, state.input_p, state.profile)
    if state.strict_errors and state.repair_loop:
        _run_repair_loop_until_stable(state)

    if not state.strict_errors:
        if state.profile in {"obsidian_kb", "curated_obsidian_kb"}:
            _stderr_log("info", "obsidian_export", "Rendering Obsidian output after quality gates passed")
            from .. import obsidian_kb as obsidian_mod
            obsidian_mod.render_obsidian_vault(
                blocks=state.blocks,
                run_dir=str(state.run_dir),
                source_title=_source_title_for_render(state.input_p, state.converted_path),
                source_hash=state.file_hash,
                run_id=state.run_id,
                profile=state.profile,
                template_name=obsidian_mod.template_for_profile(state.profile),
            )
        state.latest_outputs = _publish_latest_outputs(state.run_dir, state.root_p, state.input_p, state.profile)
        _apply_artifact_policy(state.root_p, state.run_dir, state.artifact_policy)
        state.latest_file.write_text(json.dumps({
            "source_sha256": state.file_hash,
            "run_id": state.run_id,
            "source_type": state.source_type,
            "input_path": str(state.input_p),
            "run_dir": str(state.run_dir),
            "latest_outputs": state.latest_outputs,
            "timestamp": time.time(),
            "plugin_version": state.plugin_version,
            "mineru_version": state.mineru_version,
            "runtime_cache_key": state.runtime_cache_key,
            "runtime": state.runtime,
        }, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        _stderr_log("warn", "quality_check", "Strict errors: latest.json NOT updated")

    run_outputs = _run_outputs(state)
    if state.strict_errors:
        fail(
            "E_QA_FAILED",
            "Quality gate failed; latest outputs were not published.",
            details={
                "run_id": state.run_id,
                "run_dir": str(state.run_dir),
                "outputs": run_outputs,
                "strict_errors": state.strict_errors,
                "quality_gates": state.quality_report.get("quality_gates", []),
                "next_actions": state.quality_report.get("next_actions", []),
                "quality_tasks": state.quality_report.get("quality_tasks", {}),
                "repair_artifacts": state.repair_artifacts,
                "repair_results": state.repair_results,
                "latest_outputs": state.latest_outputs,
            },
            warnings=state.warnings,
            recoverable=True,
            suggested_action="Inspect quality_report.json, discarded.md, and review_needed.md in run_dir, then adjust the input or rules and rerun.",
        )
        return

    chunks_dir = state.run_dir / "chunks"
    ok(data={
        "ok": True,
        "run_id": state.run_id,
        "run_dir": str(state.run_dir),
        "latest_outputs": state.latest_outputs,
        "outputs": run_outputs,
        "chunk_count": len(list(chunks_dir.glob("*.md"))) if chunks_dir.exists() else 0,
        "warnings": state.warnings,
        "strict_errors": state.strict_errors,
    }, warnings=state.warnings)


def _run_repair_loop_until_stable(state: PipelineState) -> None:
    assert state.run_dir is not None
    from .. import repair_loop as repair_mod

    while state.strict_errors and state.repair_iteration <= state.max_quality_iterations:
        diagnosis = repair_mod.build_failure_diagnosis(state=state)
        actions = repair_mod.build_repair_actions(state=state, diagnosis=diagnosis)
        state.repair_artifacts = repair_mod.write_repair_artifacts(
            state=state,
            diagnosis=diagnosis,
            actions=actions,
        )
        if state.repair_iteration >= state.max_quality_iterations:
            _stderr_log("warn", "repair_loop", "Quality loop iteration limit reached")
            break

        result = repair_mod.apply_safe_repairs(state=state, actions=actions)
        state.repair_results.append(result)
        (state.run_dir / "repair_result.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        if result.get("applied_count", 0) <= 0:
            _stderr_log("warn", "repair_loop", "No safe automatic repair could be applied")
            break

        state.repair_iteration += 1
        _stderr_log("info", "repair_loop", f"Applied {result.get('applied_count', 0)} repair action(s); rerunning quality checks")
        _rerender_and_recheck_after_repair(state)


def _rerender_and_recheck_after_repair(state: PipelineState) -> None:
    state.strict_errors = []
    state.warnings = []
    _stage_render_outputs(state)
    _stage_split(state)
    _stage_quality_check(state)
    _stage_audit(state)


def _run_outputs(state: PipelineState) -> dict[str, Any]:
    assert state.run_dir is not None
    chunks_dir = state.run_dir / "chunks"
    obsidian_complete = _obsidian_complete_path(state.run_dir / "obsidian")
    return {
        "converted_md": str(state.run_dir / "converted.md"),
        "normalized_md": str(state.run_dir / "normalized.md"),
        "diagnosis_report": str(state.run_dir / "diagnosis_report.json"),
        "blocks_jsonl": str(state.run_dir / "blocks.jsonl"),
        "cleaned_md": str(state.run_dir / "cleaned.md"),
        "discarded_md": str(state.run_dir / "discarded.md"),
        "review_needed_md": str(state.run_dir / "review_needed.md"),
        "audit_md": str(state.run_dir / "audit.md"),
        "quality_report": str(state.run_dir / "quality_report.json"),
        "chunks_dir": str(chunks_dir),
        "parts_dir": str(state.run_dir / "parts"),
        "images_dir": str(state.run_dir / "images"),
        "obsidian_dir": str(state.run_dir / "obsidian") if (state.run_dir / "obsidian").exists() else None,
        "obsidian_index": str(state.run_dir / "obsidian" / "00-索引.md") if (state.run_dir / "obsidian" / "00-索引.md").exists() else None,
        "obsidian_complete": str(obsidian_complete) if obsidian_complete else None,
        "review_pack": str(state.run_dir / "review_pack.json") if (state.run_dir / "review_pack.json").exists() else None,
    }


def _handle_pipeline_error(state: PipelineState, error: PipelineError) -> None:
    _stderr_log("error", "pipeline", error.message, error.code)
    details = dict(error.details)
    details.update(_write_error_report_from_context(state.error_context(), error.code, error.message, state.warnings))
    fail(error.code, error.message, details=details, warnings=state.warnings)


def _handle_missing_mineru(state: PipelineState, error: FileNotFoundError) -> None:
    _stderr_log("error", "pipeline", str(error), "E_MINERU_NOT_FOUND")
    details = _write_error_report_from_context(state.error_context(), "E_MINERU_NOT_FOUND", str(error), state.warnings)
    fail(
        "E_MINERU_NOT_FOUND",
        f"MinerU not found: {error}",
        details=details,
        warnings=state.warnings,
        recoverable=False,
        suggested_action="Rebuild the KBPrep-local .kbprep/venv so MinerU is installed there.",
    )


def _handle_timeout(state: PipelineState, error: TimeoutError) -> None:
    _stderr_log("error", "pipeline", str(error), "E_TIMEOUT")
    details = _write_error_report_from_context(state.error_context(), "E_TIMEOUT", str(error), state.warnings)
    details["mineru_timeout_seconds"] = _mineru_timeout_seconds_from_env()
    fail(
        "E_TIMEOUT",
        str(error),
        details=details,
        warnings=state.warnings,
        recoverable=True,
        suggested_action="Increase config mineru_timeout_seconds, try a smaller sample first, or verify MinerU/GPU readiness with kbprep_preflight.",
    )


def _handle_unexpected_error(state: PipelineState, error: Exception) -> None:
    error_code = "E_CONVERT_FAILED" if type(error).__name__ == "MinerUProcessError" else "E_INTERNAL"
    _stderr_log("error", "pipeline", str(error), error_code)
    import traceback
    tb = traceback.format_exc()
    _stderr_log("error", "pipeline", tb)
    details = {"exception_type": type(error).__name__}
    details.update(_write_error_report_from_context(
        state.error_context(), error_code, str(error), state.warnings, traceback_text=tb,
    ))
    extra_details = getattr(error, "details", None)
    if isinstance(extra_details, dict):
        details.update(extra_details)
    fail(error_code, str(error), details=details, warnings=state.warnings)


def _write_blocks(blocks_path: Path, blocks: list[dict[str, Any]]) -> None:
    with open(blocks_path, "w", encoding="utf-8") as f:
        for block in blocks:
            f.write(json.dumps(block, ensure_ascii=False) + "\n")

def _validate_convertible_container(input_p: Path) -> None:
    """Fail fast for modern Office-like containers before invoking heavy converters."""
    zip_container_exts = {".docx", ".pptx", ".xlsx", ".epub", ".odt", ".odp", ".ods"}
    if input_p.suffix.lower() in zip_container_exts and not zipfile.is_zipfile(input_p):
        raise PipelineError(
            "E_CONVERT_INPUT_INVALID",
            f"{input_p.name} is not a valid Office ZIP container. Check whether the file is corrupted or mislabeled.",
            {"extension": input_p.suffix.lower()},
        )


def _read_direct_source(path: Path, run_dir: Path | None = None) -> str:
    return _read_direct_source_impl(path, run_dir=run_dir, html_converter=_html_to_markdown)


def _obsidian_complete_path(obsidian_dir: Path) -> Path | None:
    if not obsidian_dir.exists():
        return None
    legacy = obsidian_dir / "01-完整正文.md"
    if legacy.exists():
        return legacy
    candidates = [path for path in obsidian_dir.glob("*.md") if path.name != "00-索引.md"]
    if len(candidates) == 1:
        return candidates[0]
    return None


def _run_mineru_conversion(
    input_p: Path,
    converted_path: Path,
    run_dir: Path,
    language: str,
    mode: str,
) -> dict:
    _validate_convertible_container(input_p)
    from .. import mineru_adapter

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
    _copy_mineru_image_assets(source_md, run_dir, result)
    shutil.copy2(str(source_md), str(converted_path))
    return result


def _copy_mineru_image_assets(source_md: Path, run_dir: Path, mineru_result: dict) -> None:
    image_dirs: list[Path] = []
    direct_images = source_md.parent / "images"
    if direct_images.exists():
        image_dirs.append(direct_images)
    assets_dir = mineru_result.get("assets_dir")
    if assets_dir:
        assets_path = Path(str(assets_dir))
        if assets_path.exists():
            image_dirs.extend(path for path in assets_path.rglob("images") if path.is_dir())

    if not image_dirs:
        return
    target_images = run_dir / "images"
    copied: set[Path] = set()
    for source_images in image_dirs:
        for src in source_images.rglob("*"):
            if not src.is_file():
                continue
            rel = src.relative_to(source_images)
            dst = target_images / rel
            if dst in copied:
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dst))
            copied.add(dst)


def _copy_local_markdown_image_assets(text: str, input_path: Path, run_dir: Path) -> tuple[str, dict]:
    """Copy local Markdown/Obsidian image refs into run_dir/images and rewrite refs."""
    source_root = input_path.parent.resolve()
    target_root = run_dir / "images"
    copied: list[str] = []
    missing: list[str] = []
    skipped: list[str] = []
    warnings: list[str] = []

    def rewrite_standard(match: re.Match) -> str:
        alt = match.group(1)
        raw_target = match.group(2)
        rewritten = _copy_one_local_markdown_image(
            raw_target=raw_target,
            source_root=source_root,
            target_root=target_root,
            copied=copied,
            missing=missing,
            skipped=skipped,
        )
        if not rewritten:
            return match.group(0)
        return f"![{alt}]({rewritten})"

    def rewrite_obsidian(match: re.Match) -> str:
        raw_target = match.group(1).split("|", 1)[0].strip()
        if not _looks_like_image_reference(raw_target):
            return match.group(0)
        rewritten = _copy_one_local_markdown_image(
            raw_target=raw_target,
            source_root=source_root,
            target_root=target_root,
            copied=copied,
            missing=missing,
            skipped=skipped,
        )
        if not rewritten:
            return match.group(0)
        return f"![]({rewritten})"

    text = re.sub(r"!\[([^\]]*)\]\(([^)\n]+)\)", rewrite_standard, text)
    text = re.sub(r"!\[\[([^\]\n]+)\]\]", rewrite_obsidian, text)

    if missing:
        warnings.append(f"W_LOCAL_IMAGE_MISSING: {len(missing)} local Markdown image references were not found")
    if skipped:
        warnings.append(
            "W_LOCAL_IMAGE_SKIPPED: "
            f"{len(skipped)} local Markdown image references were outside the source folder or unsupported"
        )

    return text, {
        "local_image_assets": {
            "copied_count": len(set(copied)),
            "copied": sorted(set(copied))[:50],
            "missing_count": len(missing),
            "missing": missing[:50],
            "skipped_count": len(skipped),
            "skipped": skipped[:50],
        },
        "warnings": warnings,
    }


def _copy_one_local_markdown_image(
    raw_target: str,
    source_root: Path,
    target_root: Path,
    copied: list[str],
    missing: list[str],
    skipped: list[str],
) -> str | None:
    path_text = _markdown_image_path_part(raw_target)
    if not path_text or _is_nonlocal_markdown_image(path_text):
        return None
    if not _looks_like_image_reference(path_text):
        skipped.append(path_text)
        return None

    decoded = unquote(path_text).replace("\\", "/").split("?", 1)[0].split("#", 1)[0]
    source_path = (source_root / decoded).resolve()
    try:
        rel = source_path.relative_to(source_root)
    except ValueError:
        skipped.append(path_text)
        return None

    if not source_path.is_file():
        missing.append(path_text)
        return None

    safe_parts = [part for part in rel.parts if part not in {"", ".", ".."}]
    if safe_parts and safe_parts[0].lower() == "images":
        safe_parts = safe_parts[1:]
    if not safe_parts:
        skipped.append(path_text)
        return None
    safe_rel = Path(*safe_parts)
    target_path = target_root / safe_rel
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not target_path.exists():
        shutil.copy2(str(source_path), str(target_path))
    rewritten = "images/" + safe_rel.as_posix()
    copied.append(rewritten)
    return rewritten


def _markdown_image_path_part(raw_target: str) -> str:
    target = raw_target.strip()
    if target.startswith("<") and ">" in target:
        return target[1:target.index(">")].strip()
    return re.sub(r"\s+(?:\"[^\"]*\"|'[^']*'|\([^)]+\))\s*$", "", target).strip()


def _is_nonlocal_markdown_image(path_text: str) -> bool:
    return bool(re.match(r"^(?:https?:)?//|^data:|^mailto:|^#", path_text, re.IGNORECASE))


def _looks_like_image_reference(path_text: str) -> bool:
    clean = path_text.split("?", 1)[0].split("#", 1)[0]
    return Path(clean).suffix.lower() in IMAGE_EXTENSIONS


def _maybe_fallback_pdf_text_layer_to_mineru(
    input_p: Path,
    converted_path: Path,
    run_dir: Path,
    language: str,
    text_layer_artifacts: dict,
) -> dict | None:
    text = converted_path.read_text(encoding="utf-8") if converted_path.exists() else ""
    rejected_quality = _converted_text_quality(text)
    text_layer_artifacts["post_convert_text_quality"] = rejected_quality

    if not _pdf_text_layer_output_needs_ocr(rejected_quality):
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
    fallback["rejected_text_layer_quality"] = rejected_quality
    ocr_text = converted_path.read_text(encoding="utf-8") if converted_path.exists() else ""
    fallback["post_convert_text_quality"] = _converted_text_quality(ocr_text)
    fallback["warnings"] = [
        *fallback.get("warnings", []),
        (
            "W_PDF_TEXT_LAYER_FALLBACK_TO_OCR: text-layer conversion produced unreadable Markdown "
            f"(unreadable={rejected_quality.get('unreadable_text_ratio', 0):.2%}, "
            f"garbled={rejected_quality.get('garbled_ratio', 0):.2%}); reran MinerU in OCR mode."
        ),
    ]
    return fallback


def _converted_text_quality(text: str) -> dict:
    from ..diagnose import analyze_text_quality
    return analyze_text_quality(text)


def _pdf_text_layer_output_needs_ocr(quality: dict) -> bool:
    threshold = DIAGNOSIS_THRESHOLDS["post_convert_pdf_text_layer_unreadable"]
    return (
        quality.get("total_chars", 0) > 0
        and (
            quality.get("unreadable_text_ratio", 0) > threshold
            or quality.get("garbled_ratio", 0) > threshold
            or quality.get("mojibake_ratio", 0) > threshold
            or quality.get("replacement_char_ratio", 0) > threshold
        )
    )





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
    route_decision = _conversion_route_decision(
        input_path=input_path,
        converter=converter,
        diagnosis=diagnosis,
        mineru_artifacts=mineru_artifacts,
    )
    report = {
        "input_file": input_path.name,
        "input_extension": input_path.suffix.lower(),
        "converter": converter,
        "route_decision": route_decision,
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


def _conversion_route_decision(
    input_path: Path,
    converter: str,
    diagnosis: dict,
    mineru_artifacts: dict,
) -> dict:
    capability = diagnosis.get("capability") if isinstance(diagnosis.get("capability"), dict) else {}
    if not capability:
        capability = get_capability_for_extension(input_path.suffix.lower())

    actual_route = _actual_route_for_converter(converter, diagnosis)
    fallback_from = mineru_artifacts.get("fallback_from") or None
    fallback_applied = bool(fallback_from) or converter == "mineru_after_pdf_text_layer_fallback"
    fallback_to = actual_route if fallback_applied else None

    return {
        "declared_capability_id": capability.get("id", ""),
        "declared_route": capability.get("route", ""),
        "declared_status": capability.get("status", ""),
        "diagnosed_pipeline": diagnosis.get("recommended_pipeline", ""),
        "diagnosed_strategy": diagnosis.get("conversion_strategy", ""),
        "actual_converter": converter,
        "actual_route": actual_route,
        "fallback_applied": fallback_applied,
        "fallback_from": fallback_from,
        "fallback_to": fallback_to,
    }


def _actual_route_for_converter(converter: str, diagnosis: dict) -> str:
    if converter == "mineru_after_pdf_text_layer_fallback":
        return "mineru_ocr"
    if converter == "mineru":
        strategy = str(diagnosis.get("conversion_strategy") or "")
        if strategy in {"mineru_ocr", "mineru_mixed_text_image"}:
            return strategy
        return "mineru"
    return converter


def _run_diagnose_direct(input_path: str, output_root: str, source_type: str) -> dict:
    from ..diagnose import DiagnoseError, diagnose_file

    payload = {
        "input_path": input_path,
        "output_root": output_root,
        "source_type": source_type,
    }
    try:
        result, warnings = diagnose_file(payload)
        return {"ok": True, "data": result, "warnings": warnings}
    except DiagnoseError as exc:
        return {
            "ok": False,
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
        }


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
            "For curated Obsidian use, discard pure author bios, usernames, self-introductions, credentials, and identity wrappers when they do not carry reusable knowledge.",
            "If removing a block would break continuity, references, setup, or a later method/case, mark it review instead of discard.",
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
                    report.get("runtime_cache_key") == runtime_cache_key and
                    not report.get("strict_errors")):
                    return {"run_id": run_dir.name, "run_dir": str(run_dir)}
            except Exception:
                continue
    return None


def _write_run_metadata(
    *,
    run_dir: Path,
    run_id: str,
    input_path: Path,
    output_root: Path,
    source_type: str,
    language: str,
    mode: str,
    splitter: str,
    profile: str,
    artifact_policy: str,
    force: bool,
    file_hash: str,
    file_size: int,
    config_hash: str,
    plugin_version: str,
    mineru_version: str,
    runtime_cache_key: str,
    runtime: dict,
) -> None:
    metadata = {
        "schema": "kbprep.run_metadata.v1",
        "run_id": run_id,
        "input_path": str(input_path),
        "output_root": str(output_root),
        "prepare_payload": {
            "input_path": str(input_path),
            "output_root": str(output_root),
            "profile": profile,
            "mode": mode,
            "language": language,
            "source_type": source_type,
            "splitter": splitter,
            "artifact_policy": artifact_policy,
            "force": force,
        },
        "source_sha256": file_hash,
        "file_size": file_size,
        "config_hash": config_hash,
        "plugin_version": plugin_version,
        "mineru_version": mineru_version,
        "runtime_cache_key": runtime_cache_key,
        "runtime": runtime,
        "created_at": time.time(),
    }
    (run_dir / "run_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _update_run_metadata(run_dir: Path, updates: dict) -> None:
    metadata_path = run_dir / "run_metadata.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    except Exception:
        metadata = {}
    metadata.update(updates)
    metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _source_identity_for_rules(input_path: Path, data: dict) -> dict:
    identity: dict = {
        "input_path": str(input_path),
        "source_path": str(input_path),
        "source_name": input_path.name,
    }

    raw_identity = data.get("source_identity")
    if isinstance(raw_identity, dict):
        _merge_identity_values(identity, raw_identity)
    elif isinstance(raw_identity, str) and raw_identity.strip():
        identity["source_identity"] = raw_identity.strip()

    source_metadata = data.get("source_metadata")
    if isinstance(source_metadata, dict):
        identity["source_metadata"] = source_metadata
        _merge_identity_values(identity, source_metadata)

    for key in (
        "source_url",
        "source_domain",
        "site_name",
        "origin",
        "origin_url",
        "source_title",
    ):
        value = _identity_scalar(data.get(key))
        if value:
            identity[key] = value

    if "source_domain" not in identity:
        domain = _domain_from_identity_url(identity.get("source_url") or identity.get("origin_url"))
        if domain:
            identity["source_domain"] = domain

    return identity


def _merge_identity_values(identity: dict, values: dict) -> None:
    for key in (
        "source_url",
        "source_domain",
        "site_name",
        "origin",
        "origin_url",
        "source_title",
    ):
        if key not in identity:
            value = _identity_scalar(values.get(key))
            if value:
                identity[key] = value


def _identity_scalar(value) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    return ""


def _domain_from_identity_url(value) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    parsed = urlparse(value.strip())
    domain = parsed.netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain




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
    return _generate_audit_from_context(AuditContext(
        input_name=input_name,
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
    ))
