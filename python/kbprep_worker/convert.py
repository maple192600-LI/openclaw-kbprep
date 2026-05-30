"""
convert — file conversion orchestrator.
Handles: PDF, DOCX, PPTX, XLSX, image, MD, TXT.
For PDF/DOCX/XLSX/image → delegates to MinerU.
For MD/TXT → direct copy with encoding normalization.
"""
import shutil
import logging
from pathlib import Path

from .envelope import ok, fail
from .detect import detect_source_type
from .mineru_adapter import run_mineru
from .supported_formats import (
    CODE_EXTENSIONS,
    CODE_LANGUAGE_BY_EXTENSION,
    DIRECT_EXTENSIONS,
    MINERU_EXTENSIONS,
    NOTEBOOK_EXTENSIONS,
)

logger = logging.getLogger(__name__)


def run(data: dict) -> None:
    input_path = data["input_path"]
    output_dir = data["output_dir"]
    language = data.get("language", "ch")
    mode = data.get("mode", "auto")
    keep_debug_files = data.get("keep_debug_files", False)

    warnings: list[str] = []
    input_p = Path(input_path)
    output_p = Path(output_dir)

    if not input_p.exists():
        fail("KBPREP_INVALID_INPUT", f"Input file does not exist: {input_path}")

    ext = input_p.suffix.lower()
    source_type = detect_source_type(input_path)

    try:
        if ext in MINERU_EXTENSIONS:
            # Delegate to MinerU
            result = run_mineru(
                input_path=str(input_p),
                output_dir=str(output_p),
                language=language,
                mode=mode,
                keep_debug_files=keep_debug_files,
            )
            warnings.extend(result.get("warnings", []))

        elif ext in DIRECT_EXTENSIONS:
            # Direct copy with encoding normalization
            output_p.mkdir(parents=True, exist_ok=True)
            source_md = output_p / "source.md"

            # Try UTF-8 first, then GBK, then latin-1
            text = None
            for enc in ["utf-8", "utf-8-sig", "gbk", "gb2312", "latin-1"]:
                try:
                    text = input_p.read_text(encoding=enc)
                    break
                except (UnicodeDecodeError, LookupError):
                    continue

            if text is None:
                fail("KBPREP_CONVERT_FAILED", f"Could not decode {input_p.name} with any known encoding.")

            if ext in CODE_EXTENSIONS:
                lang = CODE_LANGUAGE_BY_EXTENSION.get(ext, "")
                body = text.rstrip()
                fence = "```"
                while fence in body:
                    fence += "`"
                text = f"{fence}{lang}\n{body}\n{fence}\n"
            elif ext in NOTEBOOK_EXTENSIONS:
                from .notebook import notebook_to_markdown
                text = notebook_to_markdown(input_p)

            source_md.write_text(text, encoding="utf-8")
            result = {
                "source_md_path": str(source_md),
                "content_list_path": None,
                "content_list_v2_path": None,
                "middle_json_path": None,
                "assets_dir": None,
                "warnings": [],
            }

        else:
            fail("KBPREP_UNSUPPORTED_SOURCE_TYPE",
                 f"Unsupported file extension: {ext}. Supported: {', '.join(sorted(MINERU_EXTENSIONS | DIRECT_EXTENSIONS))}")

        ok(data=result, warnings=warnings)

    except FileNotFoundError as e:
        fail("KBPREP_MINERU_NOT_FOUND", str(e), recoverable=False,
             suggested_action="Rebuild the plugin-local .kbprep/venv so MinerU is installed there.")
    except TimeoutError as e:
        fail("KBPREP_WORKER_TIMEOUT", str(e), recoverable=True,
             suggested_action="Increase timeout or try with mode='ocr' for scanned docs.")
    except Exception as e:
        logger.exception("Conversion failed")
        fail("KBPREP_CONVERT_FAILED", str(e), details={"input": input_path})
