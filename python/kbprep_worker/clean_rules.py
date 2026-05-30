"""
clean_rules — rule-based noise removal for converted Markdown.
Only removes pollution sources, never summarizes body text.
"""
import re
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ── Patterns for removable noise ──────────────────────────────────

NOISE_PATTERNS: list[tuple[str, str]] = [
    # QR code / WeChat / course promotions
    (r"(?i)(扫码|加微信|关注主播|购买课程|直播间福利|免费领取|限时优惠).*$", "qr_code_caption"),
    (r"(?i)(关注公众号|扫码关注|长按识别|二维码).*$", "qr_code_caption"),
    (r"(?i)(添加微信|微信号|wx[:\s]).*$", "qr_code_caption"),
    # Watermarks / headers / footers
    (r"(?i)^(水印|仅供.*内部|版权所有|未经授权).*$", "watermark"),
    (r"(?i)^(第\s*\d+\s*页|page\s*\d+).*$", "page_number"),
    # Platform recommendations
    (r"(?i)(推荐语|平台推荐|编辑推荐|本书推荐).*$", "platform_recommendation"),
    # Disclaimer templates
    (r"(?i)(免责声明|版权声明|本文.*代表.*观点).*$", "disclaimer_template"),
    # Download/ad noise
    (r"(?i)(下载站|免费下载|点击下载|资源来自).*$", "download_ad"),
    # OCR garbled blocks (consecutive non-CJK non-ASCII noise)
    (r"^[^\u4e00-\u9fff\u3000-\u303fa-zA-Z0-9\s.,;:!?()\-]{20,}$", "ocr_garbled"),
    # Empty placeholder image descriptions
    (r"^!\[.*\]\(\s*\)$", "empty_image_placeholder"),
    # Cover marketing with no substance
    (r"(?i)^(全彩图解|精装版|畅销|重磅|全新升级|限量).*$", "cover_marketing"),
    # Copyright page noise (only match key-value lines like "定价：58元")
    (r"^(出版|印刷|发行|定价|开本|印张|字数|版次|印次)[：:].{1,30}$", "copyright_page_noise"),
]

COMPILED_PATTERNS = [(re.compile(p, re.MULTILINE), reason) for p, reason in NOISE_PATTERNS]


@dataclass
class CleanOp:
    op: str = "delete_span"
    reason: str = ""
    start_line: int = 0
    end_line: int = 0
    char_count: int = 0
    sample: str = ""


@dataclass
class CleanResult:
    cleaned_text: str = ""
    ops: list[CleanOp] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def clean_source(text: str) -> CleanResult:
    """
    Apply rule-based cleaning to converted Markdown.
    Returns cleaned text and a list of operations performed.
    """
    lines = text.split("\n")
    result = CleanResult()
    cleaned_lines: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            cleaned_lines.append(line)
            i += 1
            continue

        matched = False
        for pattern, reason in COMPILED_PATTERNS:
            if pattern.search(stripped):
                op = CleanOp(
                    reason=reason,
                    start_line=i + 1,
                    end_line=i + 1,
                    char_count=len(stripped),
                    sample=stripped[:80],
                )
                result.ops.append(op)
                matched = True
                i += 1
                break

        if not matched:
            cleaned_lines.append(line)
            i += 1

    result.cleaned_text = "\n".join(cleaned_lines)
    return result
