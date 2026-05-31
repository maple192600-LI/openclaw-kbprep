"""Block classification for the kbprep cleaning pipeline.

The classifier is deliberately conservative: protected knowledge content wins
before pollution patterns run. This prevents tutorial steps, case reviews, and
platform-rule examples from being deleted just because they mention CTA words.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


TRANSCRIPT_FILLER_RE = re.compile(
    r"^\s*(?:"
    r"\u5927\u5bb6\u597d|hello\s*\u5927\u5bb6\u597d|\u6b22\u8fce\u6765\u5230|"
    r"\u611f\u8c22(?:\u5927\u5bb6)?\u89c2\u770b|\u8c22\u8c22\u5927\u5bb6|"
    r"(?:\u672c\u671f|\u4eca\u5929)(?:.{0,12})(?:\u5230\u8fd9\u91cc|\u5c31\u5230\u8fd9\u91cc)|"
    r"\u8bb0\u5f97(?:\u70b9\u8d5e|\u5173\u6ce8|\u6536\u85cf|\u8f6c\u53d1|\u4e09\u8fde).{0,20}|"
    r"\u70b9\u8d5e\u5173\u6ce8.{0,20}|\u4e0b\u671f\u89c1|\u62dc\u62dc|bye\s*bye"
    r")[\s\u3002\uff01!\uff1f?]*$",
    re.IGNORECASE,
)

CTA_RE = re.compile(
    r"\u626b\u7801(?:\u52a0\u5165|\u5165\u7fa4|\u8fdb\u7fa4|\u52a0\u7fa4)|"
    r"\u4e8c\u7ef4\u7801|\u957f\u6309\u8bc6\u522b|"
    r"\u6dfb\u52a0(?:\u5fae\u4fe1|\u597d\u53cb|\u5ba2\u670d|\u670d\u52a1\u53f7)|"
    r"\u5fae\u4fe1\u53f7|\u514d\u8d39\u9886\u53d6|\u9886\u53d6\u798f\u5229|"
    r"\u4f53\u9a8c\u5361|\u7acb\u5373\u8d2d\u4e70|\u9650\u65f6\u4f18\u60e0|"
    r"\u70b9\u51fb\u94fe\u63a5\u8d2d\u4e70",
    re.IGNORECASE,
)

REFUND_RE = re.compile(r"3\s*\u5929\u65e0\u7406\u7531\u9000\u6b3e", re.IGNORECASE)
FOOTER_RE = re.compile(r"^(?:\u7b2c\s*\d+\s*\u9875|page\s*\d+)$", re.IGNORECASE)

EVIDENCE_PATTERNS = [
    (re.compile(r"\u6838\u5fc3\u6743\u76ca|\u793e\u7fa4\u6743\u76ca|\u8bad\u7ec3\u8425", re.IGNORECASE), "community_benefit"),
    (re.compile(r"\u5b9e\u529b\u80cc\u4e66|\u5408\u4f5c\u4f19\u4f34|\u5b66\u5458\u8bc4\u4ef7", re.IGNORECASE), "testimonial"),
    (re.compile(r"\u64ad\u653e\u91cf|\u7c89\u4e1d\u6570|\u6536\u5165.*(?:\u6708\u5165|\u5e74\u5165)", re.IGNORECASE), "revenue_claim"),
    (re.compile(r"\u6392\u884c\u699c|\u699c\u5355|TOP\s*\d+", re.IGNORECASE), "revenue_claim"),
]

STEP_RE = re.compile(
    r"^\s*(?:\d+[\.\)\u3001]\s+|"
    r"step\s*\d+[\uff1a:\.\)\-\s]+|"
    r"\u7b2c?[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\u767e\u5343\u4e07\d]+"
    r"(?:\u6b65|\u6b65\u9aa4)?[\uff1a:\u3001\.\s]|"
    r"\u6b65\u9aa4\s*[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\u767e\u5343\u4e07\d]+"
    r"[\uff1a:\u3001\.\s])",
    re.MULTILINE | re.IGNORECASE,
)

PROMPT_RE = re.compile(r"\u63d0\u793a\u8bcd|prompt|\u6307\u4ee4|\u547d\u4ee4", re.IGNORECASE)
TOOL_RE = re.compile(
    r"\u5de5\u5177\u540d|\u5e73\u53f0\u540d|APP|\u7f51\u7ad9|\u94fe\u63a5|"
    r"\u8d26\u53f7\u8bbe\u7f6e|\u53c2\u6570|\u540e\u53f0|threshold|retry_count",
    re.IGNORECASE,
)


def classify_blocks(blocks: list[dict]) -> list[dict]:
    """Assign type, status, protection, and confidence to each block."""
    for block in blocks:
        text = block.get("text", "").strip()
        if not text:
            block["status"] = "discard"
            block["type"] = "empty"
            block["reason"] = "empty block"
            continue

        block_type = block.get("type")

        if block_type in {"code", "table", "section_heading", "quote"}:
            block["status"] = "keep"
            block["confidence"] = 0.90
            if block_type in {"code", "table"}:
                block["protected"] = True
            continue

        if block_type in {"image_evidence", "image_operation", "diagram"}:
            block["status"] = "unclassified"
            block["confidence"] = 0.0
            continue

        if block_type in {"operation_step", "case_step", "tool_instruction", "prompt"}:
            block["status"] = "keep"
            block["protected"] = True
            block["confidence"] = 0.90
            continue

        protected_type = _protected_type(text)
        if protected_type:
            block["status"] = "keep"
            block["type"] = protected_type
            block["protected"] = True
            block["confidence"] = 0.90
            continue

        if _is_contextual_cta_knowledge(text):
            block["status"] = "keep"
            block["type"] = "case_step"
            block["protected"] = True
            block["reason"] = "CTA phrase appears inside a case, rule, or handling step"
            block["confidence"] = 0.88
            continue

        discard_type = _discard_type(text)
        if discard_type:
            block["status"] = "discard"
            block["type"] = discard_type
            block["reason"] = f"matches discard pattern: {discard_type}"
            block["confidence"] = 0.95
            continue

        evidence_type = _evidence_type(text)
        if evidence_type:
            block["status"] = "evidence"
            block["type"] = evidence_type
            block["reason"] = f"matches evidence pattern: {evidence_type}"
            block["confidence"] = 0.85
            continue

        if _is_garbled(text):
            block["status"] = "discard"
            block["type"] = "garbled_text"
            block["reason"] = "garbled text detected"
            block["confidence"] = 0.80
            continue

        block["status"] = "keep"
        block["confidence"] = 0.70

    return blocks


def _protected_type(text: str) -> str | None:
    if STEP_RE.search(text):
        return "operation_step"
    if text.startswith("```"):
        return "code"
    if text.startswith("|") or "<table" in text.lower():
        return "table"
    if PROMPT_RE.search(text):
        return "prompt"
    if TOOL_RE.search(text):
        return "tool_instruction"
    return None


def _discard_type(text: str) -> str | None:
    if TRANSCRIPT_FILLER_RE.search(text):
        return "transcript_filler"
    if CTA_RE.search(text):
        return "marketing_cta"
    if REFUND_RE.search(text):
        return "refund_policy"
    if FOOTER_RE.search(text):
        return "footer"
    return None


def _evidence_type(text: str) -> str | None:
    for pattern, label in EVIDENCE_PATTERNS:
        if pattern.search(text):
            return label
    return None


def _is_garbled(text: str) -> bool:
    """Check if text is garbled while avoiding false positives on Chinese."""
    if len(text) < 20:
        return False
    garbled_chars = sum(1 for c in text if ord(c) > 127 and not ("\u4e00" <= c <= "\u9fff"))
    return garbled_chars / len(text) > 0.3


def _is_contextual_cta_knowledge(text: str) -> bool:
    """Keep CTA-like phrases when they are the object of a lesson or case."""
    cta_terms = [
        "\u626b\u7801", "\u4e8c\u7ef4\u7801", "\u957f\u6309\u8bc6\u522b",
        "\u5165\u7fa4", "\u8fdb\u7fa4", "\u52a0\u7fa4", "\u793e\u7fa4",
        "\u4f53\u9a8c\u5361", "\u9886\u53d6\u798f\u5229",
        "\u514d\u8d39\u9886\u53d6", "\u8d2d\u4e70\u5f15\u5bfc",
    ]
    if not any(term in text for term in cta_terms):
        return False

    knowledge_terms = [
        "\u6848\u4f8b", "\u590d\u76d8", "\u5e73\u53f0\u89c4\u5219",
        "\u8fdd\u89c4", "\u5224\u65ad\u6807\u51c6", "\u5904\u7406\u65b9\u5f0f",
        "\u5904\u7406\u52a8\u4f5c", "\u5b57\u6bb5", "\u53c2\u6570",
        "\u9608\u503c", "\u5224\u5b9a", "\u6807\u8bb0", "\u8bb0\u5f55",
        "risk_label", "failure_reason", "\u4e0d\u8981\u76f4\u63a5\u5220\u9664",
        "\u4e0d\u80fd\u53ea\u56e0\u4e3a", "\u4fdd\u7559\u5b8c\u6574\u4e0a\u4e0b\u6587",
        "\u6e05\u6d17", "\u6c61\u67d3", "\u6c61\u67d3\u6e90", "\u6b63\u6587",
        "\u8bef\u5220", "\u5220\u9519", "\u8303\u56f4", "\u6d4b\u8bd5",
        "\u56fe\u7247\u6e05\u6d17", "\u8425\u9500\u56fe", "\u4e8c\u7ef4\u7801\u56fe",
        "cleaned.md", "discarded.md", "review_needed.md",
    ]
    if any(term in text for term in knowledge_terms):
        return True

    return bool(re.search(
        r"(\u5982\u679c|\u5f53|\u51fa\u73b0).{0,40}"
        r"(\u626b\u7801|\u5165\u7fa4|\u52a0\u7fa4|\u793e\u7fa4|\u4f53\u9a8c\u5361).{0,60}"
        r"(\u4fdd\u7559|\u6807\u8bb0|\u8bb0\u5f55|\u5224\u65ad|\u5224\u5b9a|\u5220\u9664)",
        text,
    ))
