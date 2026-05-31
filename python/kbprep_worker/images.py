"""
classify_images - image classification.
Improved: reads context from converted.md directly instead of relying on block neighbors.
"""
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Image classification patterns ─────────────────────────────────

# QR code / CTA indicators
QR_INDICATORS = re.compile(
    r"扫码|二维码|扫一扫|QR\s*code|qrcode|加微信|添加.*服务官|"
    r"免费领取|体验卡|关注公众号|长按识别|小助手|全勤打卡|退款",
    re.IGNORECASE
)

# Marketing indicators
MARKETING_INDICATORS = re.compile(
    r"课程|训练营|报名|优惠|限时|特价|原价|现价|"
    r"核心权益|社群|学员|背书|合作伙伴|排行榜|榜单|TOP",
    re.IGNORECASE
)

# Operation/tutorial indicators
OPERATION_INDICATORS = re.compile(
    r"步骤|操作|设置|配置|界面|页面|按钮|菜单|"
    r"工具|平台|网站|APP|后台|管理|截图|如图|下图",
    re.IGNORECASE
)

# Revenue/proof indicators
PROOF_INDICATORS = re.compile(
    r"收入|月入|年入|播放量|粉丝|数据|成绩|案例|成果|变现",
    re.IGNORECASE
)


def classify_images(blocks: list[dict], run_dir: str) -> list[dict]:
    """
    Classify images based on context from converted.md.
    Reads the original converted.md to find surrounding text for each image.
    """
    # Read converted.md for full context
    run_p = Path(run_dir)
    converted_path = run_p / "converted.md"
    converted_text = ""
    if converted_path.exists():
        converted_text = converted_path.read_text(encoding="utf-8")

    # Build a map of image src -> surrounding context from converted.md
    img_context_map = {}
    if converted_text:
        img_context_map = _build_image_context_map(converted_text)

    for block in blocks:
        block_type = block.get("type", "")
        images = block.get("images", [])

        if not images:
            continue

        # Only process image-type blocks
        if block_type not in ("image_evidence", "image_operation", "diagram", "unknown_review"):
            continue

        # Get context from converted.md for each image in this block
        all_context = []
        for img in images:
            src = img.get("src", "")
            ctx = img_context_map.get(src, "")
            if ctx:
                all_context.append(ctx)

        # Also include the block's own text and heading path
        block_text = block.get("text", "")
        heading_text = " ".join(block.get("heading_path", []))
        nearby_context = " ".join(all_context)

        combined = block_text + " " + nearby_context + " " + heading_text

        img_type, status, reason = _classify(combined, block.get("heading_path"))

        block["image_type"] = img_type
        # Don't downgrade from discard to review
        if block.get("status") != "discard":
            block["status"] = status
        block["reason"] = reason

    return blocks


def _build_image_context_map(converted_text: str) -> dict[str, str]:
    """
    Build a map of image_src -> surrounding_text from converted.md.
    Looks at 5 lines before and 3 lines after each image reference.
    """
    lines = converted_text.split("\n")
    img_re = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
    context_map: dict[str, str] = {}
    context_window = 5  # lines before
    context_after = 3   # lines after

    for i, line in enumerate(lines):
        matches = list(img_re.finditer(line))
        if not matches:
            continue

        # Gather context from surrounding lines
        start = max(0, i - context_window)
        end = min(len(lines), i + context_after + 1)
        context_lines = []
        for j in range(start, end):
            if j != i:  # Skip the image line itself
                context_lines.append(lines[j].strip())

        context = " ".join(l for l in context_lines if l)

        for m in matches:
            src = m.group(2)
            if src not in context_map:
                context_map[src] = context
            else:
                # Append additional context
                context_map[src] += " " + context

    return context_map


def _classify(text: str, heading_path: list[str] = None) -> tuple[str, str, str]:
    """Classify based on combined context text and heading path."""
    if not text.strip():
        return "unknown_image", "review", "no context available"

    # QR / CTA
    if QR_INDICATORS.search(text):
        return "qr_image", "discard", "QR code or CTA image detected"

    # Revenue / proof screenshots
    if PROOF_INDICATORS.search(text):
        return "proof_screenshot", "evidence", "proof or revenue screenshot"

    # Marketing
    if MARKETING_INDICATORS.search(text):
        return "marketing_poster", "evidence", "marketing material"

    # Operation / tutorial
    if OPERATION_INDICATORS.search(text):
        return "operation_screenshot", "keep", "operation or tutorial screenshot"

    # Heading-based classification: if in educational section, keep
    if heading_path:
        heading_text = " ".join(heading_path).lower()
        edu_indicators = [
            "教程", "步骤", "操作", "设置", "配置", "如何", "怎么",
            "方法", "案例", "实战", "实操", "入门", "进阶",
            "底层逻辑", "原理", "机制", "策略", "思路",
            "公众号", "小红书", "AI", "ChatGPT", "工具",
            "打造", "赋能", "赛道", "账号", "内容",
        ]
        if any(ind in heading_text for ind in edu_indicators):
            return "operation_screenshot", "keep", "image in educational section"

    # If we have substantial context but couldn't classify
    if len(text) > 100:
        return "unknown_review", "review", f"unclassified with {len(text)} chars context"

    return "unknown_image", "review", "insufficient context for classification"
