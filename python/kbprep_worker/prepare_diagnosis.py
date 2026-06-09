"""Diagnosis report helpers for the single-file prepare pipeline."""

import json
import re
from pathlib import Path

from .converter_capabilities import get_capability_for_extension
from .title_filters import load_title_filters
from .supported_formats import (
    DIRECT_EXTENSIONS,
    EPUB_EXTENSIONS,
    FORMAT_BY_EXTENSION,
    HTML_EXTENSIONS,
    MEDIA_EXTENSIONS,
    OFFICE_XML_EXTENSIONS,
)


def write_diagnosis_report(
    run_dir: Path,
    input_path: Path,
    file_hash: str,
    source_type: str,
    diagnosis: dict,
    runtime: dict,
    warnings: list[str],
) -> None:
    fallback = diagnosis_fallback(input_path)
    capability = diagnosis.get("capability") or fallback["capability"]
    report = {
        "schema": "kbprep.diagnosis_report.v1",
        "input_file": input_path.name,
        "input_extension": input_path.suffix.lower(),
        "source_sha256": file_hash,
        "source_type": source_type,
        "detected_format": diagnosis.get("detected_format") or fallback["detected_format"],
        "recommended_pipeline": diagnosis.get("recommended_pipeline") or fallback["recommended_pipeline"],
        "conversion_strategy": diagnosis.get("conversion_strategy") or fallback["conversion_strategy"],
        "capability": capability,
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


def diagnosis_fallback(input_path: Path) -> dict:
    ext = input_path.suffix.lower()
    detected_format = FORMAT_BY_EXTENSION.get(ext, "unknown")
    capability = get_capability_for_extension(ext)
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
        "capability": capability,
    }


def source_title_for_render(input_p: Path, converted_path: Path) -> str:
    if input_p.suffix.lower() in HTML_EXTENSIONS and converted_path.exists():
        try:
            for line in converted_path.read_text(encoding="utf-8").splitlines():
                match = re.match(r"^#\s+(.+?)\s*$", line)
                if match:
                    return match.group(1).strip()
        except Exception:
            pass
    if input_p.suffix.lower() not in DIRECT_EXTENSIONS:
        title = _content_title_from_converted(converted_path)
        if title:
            return title
    return input_p.stem


def _content_title_from_converted(converted_path: Path) -> str | None:
    if not converted_path.exists():
        return None
    try:
        lines = converted_path.read_text(encoding="utf-8").splitlines()[:80]
    except Exception:
        return None

    candidates: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines):
        for candidate in _title_candidates_from_line(line):
            score = _title_candidate_score(candidate, index)
            if score > 0:
                candidates.append((score, -index, candidate))

    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][2]


def _title_candidates_from_line(line: str) -> list[str]:
    text = line.strip()
    if not text or re.match(r"^<!--\s*page:\s*\d+\s*-->$", text, re.IGNORECASE):
        return []
    text = re.sub(r"^#{1,6}\s*", "", text).strip()
    if not text:
        return []

    fragments = [text]
    for delimiter in ["✻", "|", "｜"]:
        if delimiter in text:
            fragments.append(text.split(delimiter, 1)[0].strip())
    for match in re.finditer(r"[\u4e00-\u9fff][\u4e00-\u9fffA-Za-z0-9《》「」：:·\- ]{2,39}", text):
        fragments.append(match.group(0).strip())

    candidates: list[str] = []
    seen: set[str] = set()
    for fragment in fragments:
        candidate = _normalize_title_candidate(fragment)
        if candidate and candidate not in seen:
            seen.add(candidate)
            candidates.append(candidate)
    return candidates


def _normalize_title_candidate(text: str) -> str | None:
    candidate = text.strip().strip("#*-_ \t")
    candidate = re.sub(r"\s+", " ", candidate)
    if not candidate:
        return None

    # Prefer the Chinese title in bilingual cover lines such as
    # "The Founder's Playbook创始人行动手册".
    cjk_tail = re.search(r"[A-Za-z][A-Za-z'’ -]{3,}([\u4e00-\u9fff][\u4e00-\u9fffA-Za-z0-9《》「」：:·\- ]{2,39})$", candidate)
    if cjk_tail:
        candidate = cjk_tail.group(1).strip()

    title_filters = load_title_filters()
    if title_filters.split_patterns:
        split_re = "|".join(f"(?:{pattern})" for pattern in title_filters.split_patterns)
        candidate = re.split(split_re, candidate, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    candidate = candidate.strip(" ·:：-—_")
    if not candidate:
        return None
    if re.fullmatch(r"\d{1,4}", candidate):
        return None
    return candidate


def _title_candidate_score(candidate: str, line_index: int) -> int:
    title_filters = load_title_filters()
    compact = re.sub(r"\s+", "", candidate)
    if len(compact) < 4 or len(compact) > 40:
        return 0
    if compact in {"目录", "资源", "Resources", "Contents"}:
        return 0
    structural_rejects = (r"目录", r"Chapter\d*", r"Resources")
    configured_rejects = tuple(f"(?:{pattern})" for pattern in title_filters.reject_patterns)
    if re.search("|".join([*structural_rejects, *configured_rejects]), compact, re.IGNORECASE):
        return 0

    score = 100 - min(line_index, 30)
    if re.search(r"[\u4e00-\u9fff]", compact):
        score += 20
    if re.search(r"(手册|指南|报告|白皮书|行动|Playbook|Guide|Manual|Report)", candidate, re.IGNORECASE):
        score += 15
    if re.search(r"[。！？!?；;]", candidate):
        score -= 40
    return score
