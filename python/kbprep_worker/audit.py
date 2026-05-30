"""
audit — quality audit for conversion, cleaning, and splitting.
"""
import json
import logging
import re
from pathlib import Path

from .envelope import ok, fail

logger = logging.getLogger(__name__)

# Coverage thresholds per source_type
THRESHOLDS = {
    "pdf_like": {"warn": 0.86, "fail": 0.72},
    "markdown_note": {"warn": 0.88, "fail": 0.70},
    "generic_block": {"warn": 0.80, "fail": 0.60},
}

# Retention thresholds (warn-only, never hard-fail)
RETENTION_THRESHOLDS = {
    "heading_retention": {"warn": 0.80, "label": "Heading retention"},
    "number_retention": {"warn": 0.90, "label": "Number retention"},
    "step_retention": {"warn": 0.90, "label": "Step retention"},
    "code_retention": {"warn": 0.90, "label": "Code block retention"},
    "table_retention": {"warn": 0.90, "label": "Table retention"},
}

# Patterns for protected content counting
STEP_RE = re.compile(
    r"^\s*(?:\d+[\.\)、)]\s+|第?[一二三四五六七八九十百千\d]+步[骤]?[：:、\.\s]|步骤\s*[一二三四五六七八九十百千\d]+[：:、\.\s])",
    re.MULTILINE,
)
CODE_BLOCK_RE = re.compile(r"^```[\s\S]*?^```", re.MULTILINE)
TABLE_RE = re.compile(r"<table[\s\S]*?</table>", re.IGNORECASE)
NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?(?:%|万|亿|元|美元|人|次|个|天|小时|分钟)?\b")
HEADING_RE = re.compile(r"^#{1,6}\s+.+$", re.MULTILINE)
GARBLED_RE = re.compile(r"[^\u4e00-\u9fff\u3000-\u303fa-zA-Z0-9\s.,;:!?()\-—一-龥]{10,}")


def compute_report(
    source_text: str,
    effective_text: str,
    source_type: str,
    chunks_dir: str | None = None,
) -> tuple[dict, list[str]]:
    """
    Pure function: compute audit report and warnings without envelope I/O.
    Returns (report_dict, warnings_list).
    """
    warnings: list[str] = []
    thresholds = THRESHOLDS.get(source_type, THRESHOLDS["generic_block"])

    # ── Character coverage ─────────────────────────────────────────
    source_chars = len(source_text.strip())
    effective_chars = len(effective_text.strip())
    coverage = effective_chars / source_chars if source_chars > 0 else 1.0

    # ── Heading retention ──────────────────────────────────────────
    source_headings = set(m.group(0).strip() for m in HEADING_RE.finditer(source_text))
    effective_headings = set(m.group(0).strip() for m in HEADING_RE.finditer(effective_text))
    heading_retention = len(effective_headings & source_headings) / len(source_headings) if source_headings else 1.0

    # ── Number retention ───────────────────────────────────────────
    source_numbers = NUMBER_RE.findall(source_text)
    effective_numbers = NUMBER_RE.findall(effective_text)
    number_retention = len(set(effective_numbers) & set(source_numbers)) / len(set(source_numbers)) if source_numbers else 1.0

    # ── Step retention ─────────────────────────────────────────────
    source_steps = STEP_RE.findall(source_text)
    effective_steps = STEP_RE.findall(effective_text)
    step_retention = len(effective_steps) / len(source_steps) if source_steps else 1.0

    # ── Code block retention ───────────────────────────────────────
    source_code = CODE_BLOCK_RE.findall(source_text)
    effective_code = CODE_BLOCK_RE.findall(effective_text)
    code_retention = len(effective_code) / len(source_code) if source_code else 1.0

    # ── Table retention ────────────────────────────────────────────
    source_tables = TABLE_RE.findall(source_text)
    effective_tables = TABLE_RE.findall(effective_text)
    table_retention = len(effective_tables) / len(source_tables) if source_tables else 1.0

    # ── Garbled rate ───────────────────────────────────────────────
    garbled_matches = GARBLED_RE.findall(effective_text)
    garbled_chars = sum(len(m) for m in garbled_matches)
    garbled_rate = garbled_chars / effective_chars if effective_chars > 0 else 0

    # ── Chunk analysis ─────────────────────────────────────────────
    chunk_too_long = 0
    chunk_too_short = 0
    chunk_count = 0
    if chunks_dir:
        chunks_p = Path(chunks_dir)
        if chunks_p.exists():
            for chunk_file in sorted(chunks_p.glob("*.md")):
                chunk_count += 1
                text = chunk_file.read_text(encoding="utf-8")
                # Strip frontmatter
                if text.startswith("---"):
                    end = text.find("---", 3)
                    if end > 0:
                        text = text[end + 3:].strip()
                cl = len(text)
                if cl > 6000:
                    chunk_too_long += 1
                if cl < 200:
                    chunk_too_short += 1

    # ── Build report ───────────────────────────────────────────────
    report = {
        "source_type": source_type,
        "coverage": round(coverage, 4),
        "heading_retention": round(heading_retention, 4),
        "number_retention": round(number_retention, 4),
        "step_retention": round(step_retention, 4),
        "code_retention": round(code_retention, 4),
        "table_retention": round(table_retention, 4),
        "garbled_rate": round(garbled_rate, 4),
        "chunk_count": chunk_count,
        "chunk_too_long": chunk_too_long,
        "chunk_too_short": chunk_too_short,
        "thresholds": thresholds,
        "llm_review": {
            "requested": False,
            "used": False,
            "fallback": "rules_only",
            "reason": "v0.1 rules_only mode",
        },
    }

    # ── Evaluate coverage (hard fail) ──────────────────────────────
    if coverage < thresholds["fail"]:
        msg = f"Coverage {coverage:.2%} is below fail threshold {thresholds['fail']:.0%}"
        warnings.append(f"FAIL: {msg}")

    # ── Evaluate retention metrics (warn only) ─────────────────────
    retention_values = {
        "heading_retention": heading_retention,
        "number_retention": number_retention,
        "step_retention": step_retention,
        "code_retention": code_retention,
        "table_retention": table_retention,
    }
    for key, value in retention_values.items():
        t = RETENTION_THRESHOLDS.get(key)
        if t and value < t["warn"]:
            warnings.append(f"{t['label']} low: {value:.0%} (threshold {t['warn']:.0%})")

    if garbled_rate > 0.05:
        warnings.append(f"High garbled text rate: {garbled_rate:.2%}")

    if chunk_too_long > 0:
        warnings.append(f"{chunk_too_long} chunk(s) exceed 6000 chars")

    if chunk_too_short > 0:
        warnings.append(f"{chunk_too_short} chunk(s) below 200 chars")

    return report, warnings


def run(data: dict) -> None:
    """Envelope-wrapped entry point for standalone audit calls."""
    source_md_path = data["source_md_path"]
    cleaned_md_path = data.get("cleaned_md_path")
    chunks_dir = data.get("chunks_dir")
    source_type = data["source_type"]
    allow_low_coverage = data.get("allow_low_coverage", False)

    source_p = Path(source_md_path)
    if not source_p.exists():
        fail("KBPREP_INVALID_INPUT", f"source_md_path does not exist: {source_md_path}")

    source_text = source_p.read_text(encoding="utf-8")
    cleaned_text = None
    if cleaned_md_path:
        cleaned_p = Path(cleaned_md_path)
        if cleaned_p.exists():
            cleaned_text = cleaned_p.read_text(encoding="utf-8")

    effective_text = cleaned_text or source_text
    thresholds = THRESHOLDS.get(source_type, THRESHOLDS["generic_block"])

    report, warnings = compute_report(source_text, effective_text, source_type, chunks_dir)

    # Write report
    report_path = source_p.parent / "report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    # Hard fail on coverage
    if report["coverage"] < thresholds["fail"]:
        msg = f"Coverage {report['coverage']:.2%} is below fail threshold {thresholds['fail']:.0%}"
        if not allow_low_coverage:
            fail("KBPREP_LOW_COVERAGE", msg, details=report, warnings=warnings)
        # If allow_low_coverage, warning was already added by compute_report

    ok(data=report, warnings=warnings)
