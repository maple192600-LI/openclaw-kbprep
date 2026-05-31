"""
classify_images - image classification.

Reads context from converted.md so image-only blocks can be classified by their
nearby paragraphs instead of by filename alone.
"""
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# QR code / CTA indicators
QR_INDICATORS = re.compile(
    r"扫码|二维码|扫一[扫下]|QR\s*code|qrcode|加微信|添加.*(?:客服|助理|老师)|"
    r"免费领取|体验卡|关注公众号|长按识别|小助理|全勤打卡|退款|入群|进群|社群",
    re.IGNORECASE,
)

# Marketing indicators
MARKETING_INDICATORS = re.compile(
    r"课程|训练营|报名|优惠|限时|特价|原价|现价|核心权益|学员专享|"
    r"背书|合作伙伴|排行榜|榜单|TOP|限量名额|立即购买|立即报名|sale|discount",
    re.IGNORECASE,
)

# Operation/tutorial indicators
OPERATION_INDICATORS = re.compile(
    r"步骤|操作|设置|配置|界面|页面|按钮|菜单|工具|平台|网站|APP|后台|"
    r"管理|截图|如图|下图|点击|选择|输入|保存|安装|部署|导入|导出|"
    r"step|configure|settings|dashboard|screenshot|click|select|install",
    re.IGNORECASE,
)

# Revenue/proof indicators
PROOF_INDICATORS = re.compile(
    r"收入|月入|年入|播放量|粉丝|数据|成绩|案例|成果|变现|订单|转化率|"
    r"revenue|income|views|followers|conversion",
    re.IGNORECASE,
)

EDUCATIONAL_HEADING_INDICATORS = [
    "教程", "步骤", "操作", "设置", "配置", "如何", "怎么",
    "方法", "案例", "实战", "实操", "入门", "进阶",
    "底层逻辑", "原理", "机制", "策略", "思路",
    "公众号", "小红书", "ai", "chatgpt", "工具",
    "打造", "赋能", "赛道", "账号", "内容",
]


def classify_images(blocks: list[dict], run_dir: str) -> list[dict]:
    """
    Classify images based on context from converted.md.
    Reads the original converted.md to find surrounding text for each image.
    """
    run_p = Path(run_dir)
    converted_path = run_p / "converted.md"
    converted_text = ""
    if converted_path.exists():
        converted_text = converted_path.read_text(encoding="utf-8")

    img_context_map = {}
    if converted_text:
        img_context_map = _build_image_context_map(converted_text)

    for block in blocks:
        block_type = block.get("type", "")
        images = block.get("images", [])

        if not images:
            continue

        if block_type not in ("image_evidence", "image_operation", "diagram", "unknown_review"):
            continue

        all_context = []
        for img in images:
            src = img.get("src", "")
            ctx = img_context_map.get(src, "")
            if ctx:
                all_context.append(ctx)

        block_text = block.get("text", "")
        heading_text = " ".join(block.get("heading_path", []))
        nearby_context = " ".join(all_context)
        combined = block_text + " " + nearby_context + " " + heading_text

        img_type, status, reason = _classify(combined, block.get("heading_path"))

        block["image_type"] = img_type
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
    context_window = 5
    context_after = 3

    for i, line in enumerate(lines):
        matches = list(img_re.finditer(line))
        if not matches:
            continue

        start = max(0, i - context_window)
        end = min(len(lines), i + context_after + 1)
        context_lines = []
        for j in range(start, end):
            if j != i:
                context_lines.append(lines[j].strip())

        context = " ".join(line for line in context_lines if line)

        for match in matches:
            src = match.group(2)
            if src not in context_map:
                context_map[src] = context
            else:
                context_map[src] += " " + context

    return context_map


def _classify(text: str, heading_path: list[str] = None) -> tuple[str, str, str]:
    """Classify based on combined context text and heading path."""
    if not text.strip():
        return "unknown_image", "review", "no context available"

    if QR_INDICATORS.search(text):
        return "qr_image", "discard", "QR code or CTA image detected"

    if PROOF_INDICATORS.search(text):
        return "proof_screenshot", "evidence", "proof or revenue screenshot"

    if MARKETING_INDICATORS.search(text):
        return "marketing_poster", "evidence", "marketing material"

    if OPERATION_INDICATORS.search(text):
        return "operation_screenshot", "keep", "operation or tutorial screenshot"

    if heading_path:
        heading_text = " ".join(heading_path).lower()
        if any(indicator in heading_text for indicator in EDUCATIONAL_HEADING_INDICATORS):
            return "operation_screenshot", "keep", "image in educational section"

    if len(text) > 100:
        return "unknown_review", "review", f"unclassified with {len(text)} chars context"

    return "unknown_image", "review", "insufficient context for classification"
