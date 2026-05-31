"""
mineru_adapter — wrapper around MinerU CLI for document conversion.
Handles device detection and resource control.
"""
import os
import subprocess
import logging
from pathlib import Path

from .setup_env import detect_device

logger = logging.getLogger(__name__)
DEFAULT_MINERU_TIMEOUT_SECONDS = 1140


class MinerUProcessError(RuntimeError):
    def __init__(self, message: str, details: dict):
        self.details = details
        super().__init__(message)

MINERU_LANGUAGE_ALIASES = {
    "zh": "ch",
    "zh-cn": "ch",
    "zh_cn": "ch",
    "cn": "ch",
    "chinese": "ch",
    "simplified_chinese": "ch",
    "zh-hans": "ch",
    "zh_hans": "ch",
    "zh-tw": "chinese_cht",
    "zh_tw": "chinese_cht",
    "zh-hk": "chinese_cht",
    "zh_hk": "chinese_cht",
    "traditional_chinese": "chinese_cht",
}


def find_mineru() -> str:
    """Find the MinerU executable installed beside the selected Python runtime."""
    import sys
    python_dir = Path(sys.executable).parent
    for name in ["mineru", "mineru.exe"]:
        candidate = python_dir / name
        if candidate.exists():
            return str(candidate)
    raise FileNotFoundError(f"mineru not found in selected Python environment: {python_dir}")


def normalize_mineru_language(language: str | None) -> str:
    """Map common user-facing language hints to MinerU CLI language codes."""
    if not language:
        return "ch"
    normalized = language.strip().lower()
    return MINERU_LANGUAGE_ALIASES.get(normalized, language)


def mineru_timeout_seconds() -> int:
    raw = os.environ.get("KBPREP_MINERU_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return DEFAULT_MINERU_TIMEOUT_SECONDS
    try:
        value = int(float(raw))
    except ValueError:
        return DEFAULT_MINERU_TIMEOUT_SECONDS
    return max(30, value)


def run_mineru(
    input_path: str,
    output_dir: str,
    language: str = "ch",
    mode: str = "auto",
    keep_debug_files: bool = False,
) -> dict:
    """
    Run MinerU on a single file.

    Returns dict with:
        source_md_path, content_list_path, content_list_v2_path,
        middle_json_path, assets_dir, warnings
    """
    mineru = find_mineru()
    input_p = Path(input_path)
    output_p = Path(output_dir)
    output_p.mkdir(parents=True, exist_ok=True)

    stem = input_p.stem
    assets_dir = output_p / "mineru_raw"
    assets_dir.mkdir(parents=True, exist_ok=True)

    mineru_language = normalize_mineru_language(language)
    timeout_seconds = mineru_timeout_seconds()
    cmd = [
        mineru,
        "-p", str(input_p),
        "-o", str(assets_dir),
        "-b", "pipeline",
        "-m", mode,
        "-l", mineru_language,
    ]

    logger.info("Running MinerU: %s", " ".join(cmd))

    env = os.environ.copy()

    # Keep proxy for external connections (model downloads), bypass for localhost
    env["NO_PROXY"] = "localhost,127.0.0.1"
    env["no_proxy"] = "localhost,127.0.0.1"

    # Use ModelScope for faster model downloads in China
    env["MINERU_TOOLS_SOURCE"] = "modelscope"

    # Device detection
    device = detect_device()
    env["MINERU_DEVICE_MODE"] = device

    if device == "cpu":
        env["TORCH_NUM_THREADS"] = os.environ.get("TORCH_NUM_THREADS", "4")
        env["OMP_NUM_THREADS"] = os.environ.get("OMP_NUM_THREADS", "4")
        logger.warning("Running MinerU in CPU mode. Install CUDA torch for GPU acceleration.")
    else:
        logger.info("Running MinerU on device: %s", device)

    # On Windows, lower subprocess priority to avoid starving the Gateway process
    kwargs: dict = {}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "IDLE_PRIORITY_CLASS", 0)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd=str(input_p.parent),
            env=env,
            **kwargs,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(
            f"MinerU timed out after {timeout_seconds}s processing {input_p.name}"
        ) from exc

    if result.returncode != 0:
        stderr_tail = result.stderr.strip().split("\n")[-20:] if result.stderr else []
        raise MinerUProcessError(
            f"MinerU exited with code {result.returncode}: {'; '.join(stderr_tail)}",
            details={
                "mineru_exit_code": result.returncode,
                "mineru_stderr_tail": stderr_tail,
                "mineru_stdout_tail": result.stdout.strip().split("\n")[-20:] if result.stdout else [],
                "mineru_timeout_seconds": timeout_seconds,
                "mineru_command": _redact_command(cmd),
            },
        )

    # Locate MinerU output files
    possible_roots = [
        assets_dir / stem,
        assets_dir / stem / "auto",
        assets_dir / stem / "ocr",
        assets_dir / "auto" / stem,
        assets_dir / "ocr" / stem,
    ]

    md_path = None
    content_list = None
    content_list_v2 = None
    middle_json = None

    for root in possible_roots:
        if not root.exists():
            continue
        candidate_md = root / f"{stem}.md"
        if candidate_md.exists():
            md_path = candidate_md
        for f in root.iterdir():
            name = f.name
            if name.endswith("_content_list_v2.json"):
                content_list_v2 = f
            elif name.endswith("_content_list.json"):
                content_list = f
            elif name.endswith("_middle.json"):
                middle_json = f

    if md_path is None:
        for f in assets_dir.rglob(f"{stem}.md"):
            md_path = f
            break

    if md_path is None:
        raise RuntimeError(f"MinerU did not produce a .md file for {input_p.name}")

    # Copy source.md to output_dir for easy access
    final_md = output_p / "source.md"
    final_md.write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")

    # Clean debug files if not requested
    if not keep_debug_files:
        for pdf_file in assets_dir.rglob("*.pdf"):
            if pdf_file.name.endswith("_layout.pdf") or pdf_file.name.endswith("_span.pdf"):
                pdf_file.unlink(missing_ok=True)

    warnings: list[str] = []
    if content_list is None and content_list_v2 is None:
        warnings.append("MinerU did not produce content_list files. Page-level hints unavailable for splitting.")

    return {
        "source_md_path": str(final_md),
        "content_list_path": str(content_list) if content_list else None,
        "content_list_v2_path": str(content_list_v2) if content_list_v2 else None,
        "middle_json_path": str(middle_json) if middle_json else None,
        "assets_dir": str(assets_dir),
        "warnings": warnings,
        "mineru_timeout_seconds": timeout_seconds,
        "mineru_command": _redact_command(cmd),
    }


def _redact_command(cmd: list[str]) -> list[str]:
    return [str(part) for part in cmd]
