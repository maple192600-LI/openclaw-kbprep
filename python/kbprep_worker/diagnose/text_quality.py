"""Text quality and text-profile diagnosis helpers."""

from __future__ import annotations

import re

from ..quality.thresholds import DIAGNOSIS_THRESHOLDS
from ..rule_loader import LoadedCleaningRules, load_cleaning_rules, rule_matches


# Chinese character range
CJK_RE = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf\U00020000-\U0002a6df]')
# English letters and digits
ALNUM_RE = re.compile(r'[a-zA-Z0-9]')
# Control characters (excluding common whitespace)
CONTROL_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]')
COMMON_CJK_RE = re.compile(r'[\u4e00-\u9fff]')
COMMON_NON_CJK_RE = re.compile(r'[a-zA-Z0-9\s\u3000-\u303f.,;:!?()\-—\[\]{}<>"\'/\\@#$%^&*+=|~`，。！？；：（）【】《》、]')
# Common OCR confusion patterns
OCR_AI_CONFUSION_RE = re.compile(r'\b(?:All in Al|Al编程|Al工具|A时代|Al使用|Google Al)\b')
# Garbled text: long runs of non-CJK, non-ASCII, non-common-punctuation
GARBLED_RE = re.compile(r'[^\u4e00-\u9fff\u3000-\u303fa-zA-Z0-9\s.,;:!?()\-—\[\]{}<>"\'/\\@#$%^&*+=|~`]{15,}')
# Common Chinese mojibake produced by broken PDF text layers. These are valid
# Unicode characters, so a plain CJK ratio check can miss them.
MOJIBAKE_RE = re.compile(
    r'(?:[鐩綍绔鍏姝鏄鐨瀹鏂杩鎴搴閰瑙涓叧妯鍙鎶姟鍔卞彂]{2,}|[鈥聽銆€]{1,})'
)
MOJIBAKE_CHAR_RE = re.compile(r'[鐩綍绔鍏姝鏄鐨瀹鏂杩鎴搴閰瑙涓叧妯鍙鎶姟鍔卞彂绯荤粺]')
MOJIBAKE_TOKEN_RE = re.compile(
    "|".join(
        re.escape(token)
        for token in [
            "姗欑毊", "鍏ラ棬", "绮鹃€", "娑电洊", "鏋舵瀯", "鍘熺悊", "閮ㄧ讲",
            "鏂规", "妗堛€", "娓犻亾", "鎺ュ叆", "绯荤粺", "妯″瀷", "閰嶇疆",
            "瀹夊叏", "鎴愭湰", "鍙傝€", "鎵嬪唽", "淇℃伅", "鏉ユ簮", "瀹樻柟",
            "鏂囨。", "浠撳簱", "绀惧尯", "璋冪爺", "鐗堟湰", "閫傜敤", "鍙戝竷",
            "鏃堕棿", "鐢熸€", "鍏ㄦ櫙", "鍏紬", "鐭ヨ瘑", "缂栫▼", "杈呭姪",
            "鍑嗙‘", "娆㈣繋", "鍏虫敞", "鍙嶉", "棣堜氦", "閰嶅", "瑙嗛",
        ]
    )
)


def analyze_text_quality(
    text: str,
    profile: str = "standard",
    document_type: str = "",
    rule_templates: list[str] | tuple[str, ...] | None = None,
) -> dict:
    """Analyze text quality metrics."""
    cleaning_rules = load_cleaning_rules(
        profile=profile,
        document_type=document_type,
        templates=tuple(rule_templates or ()),
    )
    if not text:
        return {
            "total_chars": 0,
            "chinese_ratio": 0.0,
            "alnum_ratio": 0.0,
            "control_ratio": 0.0,
            "garbled_ratio": 0.0,
            "garbled_chars": 0,
            "non_common_unicode_ratio": 0.0,
            "replacement_char_ratio": 0.0,
            "mojibake_ratio": 0.0,
            "mojibake_chars": 0,
            "unreadable_text_ratio": 0.0,
            "ocr_ai_confusion_count": 0,
            "has_qr_text": False,
            "has_cta_text": False,
            "cleaning_rule_sources": list(cleaning_rules.sources),
        }

    total = len(text)
    chinese_chars = len(CJK_RE.findall(text))
    alnum_chars = len(ALNUM_RE.findall(text))
    control_chars = len(CONTROL_RE.findall(text))
    garbled_matches = GARBLED_RE.findall(text)
    garbled_chars = sum(len(m) for m in garbled_matches)
    non_common_unicode_chars = sum(
        1
        for ch in text
        if ord(ch) > 127 and not COMMON_CJK_RE.match(ch) and not COMMON_NON_CJK_RE.match(ch)
    )
    replacement_chars = text.count("?") + text.count("\ufffd")
    mojibake_matches = MOJIBAKE_RE.findall(text)
    mojibake_sequence_chars = sum(len(m) for m in mojibake_matches)
    mojibake_char_count = len(MOJIBAKE_CHAR_RE.findall(text))
    mojibake_token_chars = sum(len(m.group(0)) for m in MOJIBAKE_TOKEN_RE.finditer(text))
    mojibake_chars = max(mojibake_sequence_chars, mojibake_char_count, mojibake_token_chars)
    non_common_unicode_ratio = non_common_unicode_chars / total if total > 0 else 0.0
    replacement_char_ratio = replacement_chars / total if total > 0 else 0.0
    mojibake_ratio = mojibake_chars / total if total > 0 else 0.0
    unreadable_text_ratio = max(
        garbled_chars / total if total > 0 else 0.0,
        non_common_unicode_ratio,
        mojibake_ratio,
        replacement_char_ratio
        if (chinese_chars + alnum_chars) / total < DIAGNOSIS_THRESHOLDS["replacement_char_low_signal_ratio"]
        else 0.0,
    )
    ocr_confusions = len(OCR_AI_CONFUSION_RE.findall(text))

    return {
        "total_chars": total,
        "chinese_ratio": round(chinese_chars / total, 4) if total > 0 else 0.0,
        "alnum_ratio": round(alnum_chars / total, 4) if total > 0 else 0.0,
        "control_ratio": round(control_chars / total, 4) if total > 0 else 0.0,
        "garbled_ratio": round(garbled_chars / total, 4) if total > 0 else 0.0,
        "garbled_chars": garbled_chars,
        "non_common_unicode_ratio": round(non_common_unicode_ratio, 4),
        "replacement_char_ratio": round(replacement_char_ratio, 4),
        "mojibake_ratio": round(mojibake_ratio, 4),
        "mojibake_chars": mojibake_chars,
        "unreadable_text_ratio": round(unreadable_text_ratio, 4),
        "ocr_ai_confusion_count": ocr_confusions,
        "has_qr_text": _has_qr_text(text, cleaning_rules),
        "has_cta_text": _has_cta_text(text, cleaning_rules),
        "cleaning_rule_sources": list(cleaning_rules.sources),
    }


def _has_qr_text(text: str, rules: LoadedCleaningRules) -> bool:
    return _matches_any(text, rules.qr_image_markers + rules.image_qr_indicators)


def _has_cta_text(text: str, rules: LoadedCleaningRules) -> bool:
    text_lower = text.lower()
    if any(keyword in text or keyword.lower() in text_lower for keyword in rules.cta_keywords):
        return True
    return any(rule_matches(rule, text) for rule in rules.promotional_line_rules)


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def detect_text_profile(text: str, detected_format: str = "text") -> dict:
    """Classify text shape without summarizing or rewriting it."""
    headings = len(re.findall(r'^#{1,6}\s+', text, re.MULTILINE))
    numbered_steps = len(re.findall(
        r'^\s*(?:\d+[\.\)、)]\s+|第?[一二三四五六七八九十百千\d]+步[骤]?[：:、\.\s]|步骤\s*[一二三四五六七八九十百千\d]+[：:、\.\s])',
        text,
        re.MULTILINE,
    ))
    english_numbered_steps = len(re.findall(r'^\s*step\s*\d+[\uff1a:\.\)\-\s]+', text, re.MULTILINE | re.IGNORECASE))
    numbered_steps += english_numbered_steps
    timestamp_lines = len(re.findall(r'^\s*(?:\d{1,2}:)?\d{1,2}:\d{2}(?:[.,]\d{1,3})?', text, re.MULTILINE))
    speaker_lines = len(re.findall(r'^\s*[^:\n：]{1,24}[：:]\s+\S+', text, re.MULTILINE))
    table_rows = len(re.findall(r'^\|.+\|$', text, re.MULTILINE))
    chars = len(text)

    tutorial_terms = ["步骤", "操作", "设置", "配置", "教程", "如何", "怎么", "实操", "案例", "prompt", "提示词"]
    meeting_terms = ["会议", "讨论", "主持人", "嘉宾", "提问", "回答", "访谈"]
    note_terms = ["笔记", "复盘", "心得", "思考", "总结"]
    ebook_terms = ["目录", "第一章", "第二章", "前言", "附录"]

    if headings >= 8 and chars > 12_000:
        profile = "ebook_or_long_report"
    elif detected_format == "subtitle_transcript" or timestamp_lines >= 3 or speaker_lines >= 8:
        profile = "transcript"
    elif numbered_steps >= 3 or english_numbered_steps > 0 or any(term.lower() in text.lower() for term in tutorial_terms):
        profile = "tutorial"
    elif any(term in text for term in meeting_terms):
        profile = "meeting_or_interview"
    elif any(term in text for term in note_terms):
        profile = "note"
    elif any(term in text for term in ebook_terms) and chars > 12_000:
        profile = "ebook_or_long_report"
    elif chars < 4_000:
        profile = "short_text"
    else:
        profile = "long_text"

    return {
        "text_profile": profile,
        "char_count": chars,
        "heading_count": headings,
        "numbered_step_count": numbered_steps,
        "timestamp_line_count": timestamp_lines,
        "speaker_line_count": speaker_lines,
        "table_row_count": table_rows,
    }
