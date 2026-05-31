"""
normalize - OCR fix and formatting normalization.
Only fixes formatting and OCR errors, never deletes knowledge.

Input: converted.md + MinerU JSON artifacts + images/
Output: normalized.md + normalization_report.json + ocr_fixes.jsonl
"""
import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# ── OCR fix whitelist ─────────────────────────────────────────────
# High-confidence OCR confusion patterns (AI ↔ Al ↔ A)
OCR_FIX_PATTERNS = [
    # "All in Al" → "All in AI" (word boundary aware)
    (re.compile(r'\bAll in Al\b'), "All in AI", "ai_context_fix", 0.99),
    # "Al编程" → "AI编程" (Al followed by Chinese)
    (re.compile(r'Al(?=[\u4e00-\u9fff])'), "AI", "ai_context_fix", 0.96),
    # "Al工具" → "AI工具"
    (re.compile(r'Al(?=工具|时代|使用|模型|编程|技术|应用|内容|创作|协作|问答|助手)'), "AI", "ai_context_fix", 0.96),
    # "A时代" → "AI时代" (single A before Chinese, but not common English words)
    (re.compile(r'(?<![a-zA-Z])A(?=[\u4e00-\u9fff])'), "AI", "ai_context_fix", 0.90),
    # "ClaudeCode" → "Claude Code"
    (re.compile(r'ClaudeCode'), "Claude Code", "space_fix", 0.95),
    # "Google Al Studio" → "Google AI Studio"
    (re.compile(r'Google Al Studio'), "Google AI Studio", "ai_context_fix", 0.99),
    # "YouTubeAl" → "YouTube AI"
    (re.compile(r'YouTubeAl'), "YouTube AI", "ai_context_fix", 0.99),
    # "AIlinAI" → "AI in AI" (common OCR confusion)
    (re.compile(r'AIlinAI'), "AI in AI", "ai_context_fix", 0.95),
]

# Low-confidence patterns that go to review
OCR_REVIEW_PATTERNS = [
    # Single "A" that might be "AI" (context-dependent)
    (re.compile(r'(?<![a-zA-Z])A(?![a-zA-Z])'), "AI?", "ai_context_review", 0.50),
]


def normalize(converted_text: str, run_dir: str, mineru_artifacts: dict = None) -> dict:
    """
    Normalize converted markdown: fix OCR errors, fix formatting.
    Returns dict with normalized_text, fix_count, warnings.
    """
    warnings = []
    fixes = []
    text = converted_text

    # ── Step 1: Fix HTML tables → Markdown tables ─────────────────
    text, table_fixes = _convert_html_tables(text)
    fixes.extend(table_fixes)

    # ── Step 2: Fix OCR confusions ────────────────────────────────
    for pattern, replacement, rule, confidence in OCR_FIX_PATTERNS:
        matches = list(pattern.finditer(text))
        if matches:
            for m in reversed(matches):  # Reverse to preserve offsets
                fix = {
                    "line_id": f"l_{m.start()}",
                    "before": m.group(0),
                    "after": replacement,
                    "rule": rule,
                    "confidence": confidence,
                }
                fixes.append(fix)
                text = text[:m.start()] + replacement + text[m.end():]

    # Count AI/Al confusion fixes
    ai_fix_count = sum(1 for f in fixes if f["rule"] == "ai_context_fix")
    if ai_fix_count > 0:
        warnings.append(f"W_OCR_AI_CONFUSION: {ai_fix_count} AI/Al confusion patterns fixed")

    # ── Step 3: Fix heading levels ────────────────────────────────
    text, heading_fixes = _fix_heading_levels(text)
    fixes.extend(heading_fixes)

    # ── Step 4: Fix broken code blocks ────────────────────────────
    text, code_fixes = _fix_code_blocks(text)
    fixes.extend(code_fixes)

    # ── Step 5: Fix image references ──────────────────────────────
    text, img_fixes = _fix_image_references(text, run_dir)
    fixes.extend(img_fixes)

    # ── Write reports ─────────────────────────────────────────────
    run_p = Path(run_dir)

    # ocr_fixes.jsonl
    ocr_fixes = [f for f in fixes if "ai_context" in f.get("rule", "")]
    if ocr_fixes:
        with open(run_p / "ocr_fixes.jsonl", "w", encoding="utf-8") as f:
            for fix in ocr_fixes:
                f.write(json.dumps(fix, ensure_ascii=False) + "\n")

    # table_fixes.jsonl
    tbl_fixes = [f for f in fixes if "table" in f.get("rule", "")]
    if tbl_fixes:
        with open(run_p / "table_fixes.jsonl", "w", encoding="utf-8") as f:
            for fix in tbl_fixes:
                f.write(json.dumps(fix, ensure_ascii=False) + "\n")

    # normalization_report.json
    report = {
        "total_fixes": len(fixes),
        "ocr_fixes": len(ocr_fixes),
        "table_fixes": len(tbl_fixes),
        "heading_fixes": sum(1 for f in fixes if "heading" in f.get("rule", "")),
        "code_fixes": sum(1 for f in fixes if "code" in f.get("rule", "")),
        "image_fixes": sum(1 for f in fixes if "image" in f.get("rule", "")),
    }
    (run_p / "normalization_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return {
        "normalized_text": text,
        "fix_count": len(fixes),
        "warnings": warnings,
    }


def _convert_html_tables(text: str) -> tuple[str, list[dict]]:
    """Convert HTML tables to Markdown tables."""
    fixes = []
    # Simple HTML table pattern
    table_re = re.compile(r'<table[^>]*>[\s\S]*?</table>', re.IGNORECASE)

    def replace_table(match):
        html = match.group(0)
        md_table = _html_table_to_markdown(html)
        if md_table:
            fixes.append({
                "rule": "html_table_to_markdown",
                "before": html[:100] + "..." if len(html) > 100 else html,
                "after": md_table[:100] + "..." if len(md_table) > 100 else md_table,
                "confidence": 0.85,
            })
            return md_table
        return html  # Keep original if conversion fails

    text = table_re.sub(replace_table, text)
    return text, fixes


def _html_table_to_markdown(html: str) -> str | None:
    """Convert a simple HTML table to Markdown table format."""
    try:
        # Extract rows
        row_re = re.compile(r'<tr[^>]*>([\s\S]*?)</tr>', re.IGNORECASE)
        cell_re = re.compile(r'<t[dh][^>]*>([\s\S]*?)</t[dh]>', re.IGNORECASE)

        rows = row_re.findall(html)
        if not rows:
            return None

        md_rows = []
        for row in rows:
            cells = cell_re.findall(row)
            cells = [c.strip().replace('\n', ' ') for c in cells]
            if cells:
                md_rows.append("| " + " | ".join(cells) + " |")

        if not md_rows:
            return None

        # Add header separator after first row
        if len(md_rows) > 1:
            col_count = md_rows[0].count("|") - 1
            separator = "| " + " | ".join(["---"] * max(col_count, 1)) + " |"
            md_rows.insert(1, separator)

        return "\n".join(md_rows)
    except Exception:
        return None


def _fix_heading_levels(text: str) -> tuple[str, list[dict]]:
    """Fix heading level issues (e.g., skip from H1 to H3)."""
    fixes = []
    lines = text.split("\n")
    prev_level = 0

    for i, line in enumerate(lines):
        m = re.match(r'^(#{1,6})\s+(.+)$', line)
        if m:
            level = len(m.group(1))
            if level > prev_level + 1 and prev_level > 0:
                # Fix: reduce level to prev_level + 1
                new_level = prev_level + 1
                new_line = "#" * new_level + " " + m.group(2)
                fixes.append({
                    "rule": "heading_level_fix",
                    "before": line,
                    "after": new_line,
                    "confidence": 0.80,
                })
                lines[i] = new_line
                level = new_level
            prev_level = level

    return "\n".join(lines), fixes


def _fix_code_blocks(text: str) -> tuple[str, list[dict]]:
    """Fix broken code blocks (unclosed fences)."""
    fixes = []
    lines = text.split("\n")
    in_code = False
    code_start = -1

    for i, line in enumerate(lines):
        if line.strip().startswith("```"):
            if not in_code:
                in_code = True
                code_start = i
            else:
                in_code = False

    # If code block is unclosed, close it
    if in_code and code_start >= 0:
        lines.append("```")
        fixes.append({
            "rule": "code_block_close",
            "before": "(unclosed code block)",
            "after": "```",
            "confidence": 0.90,
        })

    return "\n".join(lines), fixes


def _fix_image_references(text: str, run_dir: str) -> tuple[str, list[dict]]:
    """Fix image references to point to correct paths."""
    fixes = []
    # Fix common MinerU image path patterns
    img_re = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')

    def fix_img(match):
        alt = match.group(1)
        src = match.group(2)
        # Normalize path separators
        if "\\" in src:
            new_src = src.replace("\\", "/")
            fixes.append({
                "rule": "image_path_separator",
                "before": src,
                "after": new_src,
                "confidence": 0.95,
            })
            return f"![{alt}]({new_src})"
        return match.group(0)

    text = img_re.sub(fix_img, text)
    return text, fixes
