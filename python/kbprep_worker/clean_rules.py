"""
clean_rules - block-level cleaning rules.
Operates on blocks.jsonl, NOT on raw markdown.

Each block's status is updated based on classification.
Blocks with status=discard are removed from cleaned output.
Blocks with status=evidence go to evidence/ directory.
"""
import logging
import re

logger = logging.getLogger(__name__)

PROMOTIONAL_LINE_RE = re.compile(
    r"(?:欢迎)?关注(?:公众号|视频号|小红书|B站|抖音|YouTube|频道|账号)|"
    r"(?:关注|订阅).{0,8}(?:公众号|视频号|小红书|B站|抖音|YouTube|频道|账号)|"
    r"配套视频教程[:：].*|"
    r"后续更新[:：].*|"
    r"scan the qr code.*(?:join|claim|free)|"
    r"(?:follow us on|subscribe to|sign up for free|click here to claim|claim your free)",
    re.IGNORECASE,
)

# ── CTA keywords that might appear in educational content ─────────
CONTEXTUAL_CTA_KEYWORDS = (
    "扫码", "二维码", "扫一扫", "长按识别", "微信号", "加微信",
    "添加微信", "添加好友", "公众号", "入群", "进群", "加群",
    "领取福利", "免费领取", "体验卡", "立即购买", "限时优惠",
    "scan the qr code", "follow us on", "subscribe to", "subscribe to our",
    "sign up for free", "click here to claim", "join our discord",
    "join our slack", "claim your free", "free trial group",
)

# ── Tutorial/educational indicators ───────────────────────────────
TUTORIAL_INDICATORS = (
    "教程", "步骤", "操作", "设置", "配置", "如何", "怎么",
    "方法", "流程", "指南", "实操", "案例", "实战", "手把手",
    "底层逻辑", "原理", "机制", "方法论", "策略", "思路", "心法",
    "认知", "框架", "模型", "体系", "系统", "全面", "深入",
    "入门", "进阶", "基础", "核心", "关键", "本质",
    "tutorial", "step", "guide", "how to", "setup", "workflow",
)

CONTEXTUAL_KNOWLEDGE_TERMS = (
    "案例", "复盘", "平台规则", "违规", "违规案例", "判断标准",
    "处理方式", "处理动作", "字段", "参数", "不要", "不得",
    "不能", "保留完整上下文", "如果", "当", "出现", "限制条件",
    "policy", "rule", "example", "case", "do not", "don't",
    "should not", "must not", "failure", "threshold", "retry_count",
)

# Step pattern: "1. xxx" or "1) xxx"
STEP_RE = re.compile(
    r"^\s*(?:\d+[\.\)、)]\s+|第?[一二三四五六七八九十百千\d]+步[骤]?[：:、\.\s]|步骤\s*[一二三四五六七八九十百千\d]+[：:、\.\s])",
    re.MULTILINE,
)


EN_STEP_RE = re.compile(r"^\s*step\s*\d+[\uff1a:\.\)\-\s]+", re.MULTILINE | re.IGNORECASE)


def apply_clean_rules(blocks: list[dict]) -> list[dict]:
    """
    Apply cleaning rules to classified blocks.
    Refines classification based on context.
    """
    derived_blocks: list[dict] = []
    for block in blocks:
        text = block.get("text", "").strip()
        status = block.get("status", "unclassified")
        block_type = block.get("type", "unknown")

        # Skip already-classified blocks
        if status in ("discard", "evidence"):
            continue

        promo_blocks = _split_promotional_lines(block)
        if promo_blocks:
            derived_blocks.extend(promo_blocks)
            text = block.get("text", "").strip()
            if not text:
                block["status"] = "discard"
                block["type"] = "marketing_cta"
                block["reason"] = "all lines matched promotional patterns"
                continue

        # Protected blocks are never discarded
        if block.get("protected"):
            block["status"] = "keep"
            continue

        if block_type != "section_heading" and _is_promotional_line(text):
            block["status"] = "discard"
            block["type"] = "marketing_cta"
            block["reason"] = "standalone promotional/update paragraph"
            block["risk_tags"] = block.get("risk_tags", [])
            if "promotional_line" not in block["risk_tags"]:
                block["risk_tags"].append("promotional_line")
            continue

        # Context-aware CTA check (skip headings - they're structural, not content)
        if block_type != "section_heading" and _has_cta_keywords(text) and not _is_tutorial_context(text, block):
            block["status"] = "review"
            block["risk_tags"] = block.get("risk_tags", [])
            if "possible_cta" not in block["risk_tags"]:
                block["risk_tags"].append("possible_cta")
            block["reason"] = block.get("reason", "") + " | contains CTA keywords"
            continue

        # Check for duplicate content
        if block_type == "duplicate":
            block["status"] = "discard"
            block["reason"] = "duplicate content"
            continue

    if derived_blocks:
        blocks.extend(derived_blocks)
    return blocks


def _split_promotional_lines(block: dict) -> list[dict]:
    """Move standalone promo/update lines out of mixed useful blocks."""
    text = block.get("text", "")
    if "\n" not in text:
        return []

    kept_lines: list[str] = []
    promo_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and _is_promotional_line(stripped):
            promo_lines.append(stripped)
        else:
            kept_lines.append(line)

    if not promo_lines:
        return []

    block["text"] = "\n".join(line for line in kept_lines if line.strip()).strip()
    if "promo_line_removed" not in block.setdefault("risk_tags", []):
        block["risk_tags"].append("promo_line_removed")

    derived = []
    for idx, line in enumerate(promo_lines, start=1):
        derived.append({
            "block_id": f"{block.get('block_id', 'block')}_promo_{idx:03d}",
            "source_sha256": block.get("source_sha256", ""),
            "page_start": block.get("page_start"),
            "page_end": block.get("page_end"),
            "line_start": block.get("line_start"),
            "line_end": block.get("line_end"),
            "heading_path": block.get("heading_path", []),
            "type": "marketing_cta",
            "text": line,
            "images": [],
            "status": "discard",
            "risk_tags": ["promotional_line"],
            "protected": False,
            "confidence": 0.95,
            "reason": "standalone promotional/update line split from useful block",
        })
    return derived


def _is_promotional_line(line: str) -> bool:
    if _is_contextual_promo_knowledge(line):
        return False
    return bool(PROMOTIONAL_LINE_RE.search(line))


def _is_contextual_promo_knowledge(line: str) -> bool:
    return any(term in line for term in CONTEXTUAL_KNOWLEDGE_TERMS)


def _has_cta_keywords(text: str) -> bool:
    """Check if text contains CTA-related keywords."""
    text_lower = text.lower()
    return any(kw in text or kw in text_lower for kw in CONTEXTUAL_CTA_KEYWORDS)


def _is_tutorial_context(text: str, block: dict) -> bool:
    """
    Determine if CTA keywords appear in tutorial/educational context.
    Returns True if the content is likely educational, not a CTA.
    """
    heading_path = block.get("heading_path", [])
    heading_text = " ".join(heading_path).lower()

    # Check heading path for tutorial indicators
    if any(ind in heading_text for ind in TUTORIAL_INDICATORS):
        return True

    # Check if text contains step numbers (1. 2. 3.)
    if STEP_RE.search(text) or EN_STEP_RE.search(text):
        return True

    # Check if text contains code blocks or commands
    if "```" in text or "$ " in text:
        return True

    if any(term in text for term in CONTEXTUAL_KNOWLEDGE_TERMS):
        return True

    # Check text length: CTAs are typically short (<200 chars),
    # educational content is longer
    if len(text) > 200:
        return True

    # Check if text contains analytical/educational language
    text_lower = text.lower()
    if any(ind in text_lower for ind in [
        "逻辑", "原理", "机制", "策略", "思路", "本质",
        "rule", "policy", "example", "case", "workflow", "parameter",
        "failure", "threshold", "retry", "step", "tutorial",
    ]):
        return True

    return False
