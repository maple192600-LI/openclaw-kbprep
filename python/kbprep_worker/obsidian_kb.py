"""Curated Obsidian knowledge-base rendering.

This layer runs after ordinary conversion/cleaning. It keeps source body text
verbatim, but removes knowledge-base noise such as author bios, identity
wrappers, and image-only artifacts for text-first Obsidian use.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from .render_outputs import _block_meta_comment


IMAGE_TYPES = {"image_operation", "image_evidence", "diagram", "qr_image", "unknown_image"}
DETAIL_TYPES = {"operation_step", "case_step", "tool_instruction", "prompt", "code", "table"}

AUTHOR_PREFIX_RE = re.compile(r"^(#{1,6}\s*)?(?:@?[\w\u4e00-\u9fff]{1,18})[：:]\s*(.+)$")
AUTHOR_HANDLE_RE = re.compile(r"^@[\w\u4e00-\u9fff][\w\u4e00-\u9fff._-]{0,30}$")
EMPTY_HEADING_RE = re.compile(r"^#{1,6}\s*$")
VISUAL_CHAPTER_SEPARATOR_RE = re.compile(
    r"^[=\-—_]{3,}\s*(?:第[一二三四五六七八九十百\d]+[章节篇部分]?|Chapter\s+\d+)\s*[=\-—_]{3,}$",
    re.IGNORECASE,
)
INTERNAL_PAGE_MARKER_RE = re.compile(r"^<!--\s*page:\s*\d+\s*-->$", re.IGNORECASE)
SLIDE_CHAPTER_LABEL_RE = re.compile(r"^Chapter\s+\d+\s*$", re.IGNORECASE)
SLIDE_PAGE_NUMBER_RE = re.compile(r"^\d{1,4}$")

SOCIAL_PROFILE_LABELS = [
    "讲解",
    "主讲",
    "作者",
    "整理",
    "出品",
    "分享",
]
SOCIAL_PROFILE_PLATFORMS = [
    "B站",
    "哔哩哔哩",
    "抖音",
    "小红书",
    "YouTube",
    "视频号",
    "公众号",
    "微博",
    "知乎",
]
PROVENANCE_TERMS = ["基于", "来源", "原文", "阅读原文", "出处"]

AUTHOR_BIO_TERMS = [
    "个人简介",
    "作者简介",
    "自我介绍",
    "介绍一下我自己",
    "大家好，我是",
    "大家好我是",
    "我是",
    "昵称",
    "坐标",
    "连续创业者",
    "创始人",
    "合伙人",
    "自媒体博主",
    "从业",
    "从事",
    "擅长",
    "我的背景",
    "我的经历",
]

BIO_ROLE_TERMS = [
    "博主",
    "创业者",
    "创始人",
    "合伙人",
    "操盘手",
    "负责人",
    "主理人",
    "设计师",
    "产品经理",
    "老师",
    "讲师",
    "教练",
    "专家",
    "玩家",
    "开发者",
    "创作者",
    "操盘者",
    "顾问",
    "CEO",
]

AUTHOR_CREDENTIAL_TERMS = [
    "单日获客",
    "月入",
    "年营收",
    "营收",
    "收入",
    "粉丝",
    "播放",
    "融资",
    "千万",
    "百万",
    "万+",
    "w+",
    "高客单",
    "矩阵",
    "GMV",
    "躺赚",
    "斩获",
]

KNOWLEDGE_TERMS = [
    "方法",
    "步骤",
    "流程",
    "案例",
    "复盘",
    "工具",
    "参数",
    "提示词",
    "SOP",
    "模型",
    "判断",
    "标准",
    "策略",
    "原因",
    "问题",
    "解决",
    "输入",
    "输出",
    "设置",
    "配置",
    "数据",
    "失败",
    "风险",
    "注意",
    "为什么",
    "如何",
    "怎么",
]

CASE_TERMS = ["用AI", "案例", "实战", "变现", "出海", "小红书", "公众号", "YouTube", "视频号", "矩阵"]
METHOD_TERMS = ["方法", "流程", "工作流", "SOP", "步骤", "工具", "自动化", "如何", "怎么", "重构", "提示词"]
COGNITION_TERMS = ["认知", "机会", "趋势", "为什么", "心法", "底层逻辑", "原则", "判断"]
PACKAGING_HEADING_TERMS = [
    "AI宝典",
    "宝典上线",
    "电子版",
    "版权声明",
    "致谢",
    "写在最后",
    "带着大家All in",
    "接下来",
    "赋能圈友",
    "共创篇",
    "100个圈友",
]
BRAND_HEADING_REPLACEMENTS = [
    ("生财有术在", ""),
    ("生财有术的", ""),
    ("生财有术", ""),
    ("生财准备如何用AI赋能圈友", "如何用AI赋能"),
]
LAYOUT_TABLE_TERMS = [
    "<返回",
    "返回",
    "帐户明细",
    "账号明细",
    "日期范围",
    "近7日",
    "近30日",
    "自定义",
    "广告位",
    "搜索",
    "分享",
    "收藏",
]
BRAND_PROGRAM_PACKAGING_TERMS = [
    "超级标",
    "航海体系",
    "航海一览图",
    "航海月份",
    "通过飞书表格分享",
    "课程目前正带着",
    "星球",
    "精华帖",
    "SCAI实验室",
    "航海家AI大会",
]
TRANSLATOR_BACK_MATTER_TERMS = [
    "译后记",
    "本译本仅供",
    "内部研究",
    "不做商业发行",
    "欢迎在下面这些地方找到我",
    "B 站",
    "space.bilibili.com",
    "小红书",
    "公众号",
    "YouTube",
    "官网",
    "huasheng.ai",
]


def apply_curated_obsidian_policy(blocks: list[dict]) -> list[dict]:
    """Apply text-first Obsidian curation metadata to existing blocks.

    The policy is intentionally conservative around useful knowledge. It only
    discards identity/bio noise and image-only artifacts. Content with concrete
    method or case signals is kept, and ambiguous identity-like text goes to
    review instead of being silently removed.
    """
    current_slide_chapter_title: str | None = None

    for index, block in enumerate(blocks):
        text = block.get("text", "").strip()
        if not text:
            continue

        slide_chapter_title = _slide_chapter_divider_title(text)
        if slide_chapter_title:
            current_slide_chapter_title = slide_chapter_title

        if block.get("type") in IMAGE_TYPES:
            if _is_knowledge_diagram(block):
                block["type"] = "diagram"
                block["status"] = "keep"
                block["reason"] = "keep_html_diagram_for_kb"
                block["confidence"] = max(float(block.get("confidence") or 0), 0.92)
                _append_tag(block, "html_diagram")
                continue
            _discard(block, "image_artifact", "drop_image_for_text_kb", 0.94)
            continue

        if block.get("status") != "keep":
            continue

        if _is_internal_page_marker(text):
            _discard(block, "page_marker", "drop_internal_page_marker_for_readable_kb", 0.99)
            continue

        if slide_chapter_title:
            _discard(block, "slide_chapter_divider", "drop_standalone_slide_chapter_divider_for_kb", 0.94)
            continue

        curated_chapter_text = _curated_slide_chapter_body(text, current_slide_chapter_title)
        if curated_chapter_text:
            block["curated_text"] = curated_chapter_text
            _append_tag(block, "slide_chapter_heading_normalized")
            continue

        if _is_visual_chapter_separator(text):
            _discard(block, "layout_separator", "drop_visual_chapter_separator_for_obsidian_kb", 0.95)
            continue

        if _is_translator_marketing_back_matter(text):
            _discard(block, "translator_marketing_back_matter", "drop_translator_social_back_matter_for_kb", 0.94)
            continue

        if _is_front_matter_social_profile(blocks, index, text):
            _discard(block, "author_profile_links", "drop_front_matter_author_or_social_profile_for_kb", 0.92)
            continue

        if _is_author_identity_card(blocks, index, text):
            _discard(block, "author_identity", "drop_author_identity_card_for_text_kb", 0.91)
            continue

        if block.get("type") == "table" and _is_layout_table_artifact(text):
            _discard(block, "layout_table_artifact", "drop_layout_table_for_text_kb", 0.86)
            continue

        if _is_direct_packaging_context(block):
            _discard(block, "marketing_wrapper", "drop_packaging_context_for_text_kb", 0.88)
            continue

        if _is_brand_program_packaging(text):
            _discard(block, "marketing_wrapper", "drop_brand_program_packaging_for_text_kb", 0.87)
            continue

        if _is_empty_heading(text):
            _discard(block, "empty_heading", "empty heading after source cleanup", 0.92)
            continue

        if block.get("type") == "section_heading":
            if _is_packaging_heading(text) or _is_noise_heading(text):
                _discard(block, "marketing_wrapper", "drop_packaging_heading_for_text_kb", 0.90)
                continue
            sanitized = sanitize_heading_text(text)
            if sanitized != text:
                block["curated_text"] = sanitized
                _append_tag(block, "heading_author_prefix_removed")
            continue

        if _is_author_intro(text):
            if _has_strong_knowledge_signal(text):
                block["status"] = "review"
                block["type"] = "author_intro_review"
                block["reason"] = "identity-heavy text also contains possible knowledge signals"
                block["confidence"] = 0.60
                _append_tag(block, "possible_author_intro")
            else:
                _discard(block, "author_intro", "author bio or identity wrapper unrelated to knowledge body", 0.90)
            continue

    _drop_toc_windows(blocks)
    return blocks


def render_obsidian_vault(
    blocks: list[dict],
    run_dir: str,
    source_title: str,
    source_hash: str,
    run_id: str,
) -> None:
    """Render a text-first Obsidian wiki folder under run_dir/obsidian."""
    run_p = Path(run_dir)
    vault_dir = run_p / "obsidian"
    if vault_dir.exists():
        shutil.rmtree(vault_dir)

    audit_dir = vault_dir / "_audit"
    for subdir in ["认知", "方法", "案例", "_audit", "images"]:
        (vault_dir / subdir).mkdir(parents=True, exist_ok=True)

    source_images = run_p / "images"
    vault_images = vault_dir / "images"
    if source_images.exists():
        shutil.rmtree(vault_images, ignore_errors=True)
        shutil.copytree(source_images, vault_images)

    kept_blocks = [b for b in blocks if b.get("status") == "keep" and _renderable_text(b)]
    review_blocks = [b for b in blocks if b.get("status") == "review"]
    discarded_blocks = [b for b in blocks if b.get("status") == "discard"]

    complete_body = _join_blocks(kept_blocks)
    (vault_dir / "01-完整正文.md").write_text(
        "\n".join([
            "---",
            f'title: "{_yaml_safe(source_title)}"',
            "kbprep_profile: curated_obsidian_kb",
            f'source_sha256: "{source_hash}"',
            f'run_id: "{run_id}"',
            "---",
            "",
            complete_body,
            "",
        ]),
        encoding="utf-8",
    )

    note_entries, source_map = _render_topic_notes(kept_blocks, vault_dir)
    _render_index(vault_dir, source_title, note_entries, kept_blocks, discarded_blocks, review_blocks)
    _render_audit_file(audit_dir / "discarded.md", discarded_blocks)
    _render_audit_file(audit_dir / "review_needed.md", review_blocks)
    _render_cleaning_report(
        audit_dir / "cleaning-report.md",
        source_title,
        kept_blocks,
        discarded_blocks,
        review_blocks,
        note_entries,
    )
    (audit_dir / "source-map.jsonl").write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in source_map),
        encoding="utf-8",
    )


def sanitize_heading_text(text: str) -> str:
    """Remove author/name prefixes from headings while preserving heading level."""
    if not text.strip().startswith("#"):
        return text
    match = re.match(r"^(#{1,6}\s*)(.+)$", text.strip())
    if not match:
        return text
    prefix, title = match.groups()
    title = _strip_author_prefix(title)
    title = _strip_brand_prefix(title)
    if not title:
        return text
    return f"{prefix}{title}"


def _strip_author_prefix(title: str) -> str:
    match = AUTHOR_PREFIX_RE.match(title.strip())
    if not match:
        return title.strip()
    return match.group(2).strip()


def _strip_brand_prefix(title: str) -> str:
    clean = title.strip()
    for old, new in BRAND_HEADING_REPLACEMENTS:
        clean = clean.replace(old, new)
    clean = re.sub(r"^\s*100个\s*圈友", "100个圈友", clean)
    return clean.strip(" ：:")


def _renderable_text(block: dict) -> str:
    text = (block.get("curated_text") or block.get("text") or "").strip()
    if not text:
        return ""
    if _is_internal_page_marker(text):
        return ""
    if block.get("type") in IMAGE_TYPES and not _is_knowledge_diagram(block):
        return ""
    return text


def _is_knowledge_diagram(block: dict) -> bool:
    """Keep extracted HTML/SVG diagrams as first-class knowledge assets."""
    images = block.get("images") or []
    if not images:
        return False
    if not any(str(img.get("src") or "").lower().endswith(".svg") for img in images if isinstance(img, dict)):
        return False
    text = str(block.get("text") or "")
    if re.search(r"diagram-\d+\.svg", text, re.IGNORECASE):
        return True
    heading = " ".join(str(part) for part in (block.get("heading_path") or []))
    return any(term in heading for term in ["图", "全景", "流程", "结构", "示意", "金字塔", "工作流"])


def _join_blocks(blocks: list[dict]) -> str:
    return "\n\n".join(_renderable_text(block) for block in blocks if _renderable_text(block))


def _is_internal_page_marker(text: str) -> bool:
    return bool(INTERNAL_PAGE_MARKER_RE.match(text.strip()))


def _slide_chapter_divider_title(text: str) -> str | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 3 or len(lines) > 5:
        return None
    if not SLIDE_CHAPTER_LABEL_RE.match(lines[0]):
        return None
    if not SLIDE_PAGE_NUMBER_RE.match(lines[-1]):
        return None
    title_lines = lines[1:-1]
    if any(len(line) > 40 or re.search(r"[。！？!?；;]", line) for line in title_lines):
        return None
    title = " ".join(title_lines).strip()
    if not title or len(title) > 80:
        return None
    return title


def _curated_slide_chapter_body(text: str, title_hint: str | None) -> str | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 2 or not SLIDE_CHAPTER_LABEL_RE.match(lines[0]):
        return None

    title = (title_hint or "").strip()
    body = "\n".join(_drop_trailing_slide_page_number(lines[1:])).strip()
    if not body:
        return None

    if title:
        body = _strip_slide_title_prefix(body, title)
    elif not title:
        title = lines[1].strip()
        body = "\n".join(_drop_trailing_slide_page_number(lines[2:])).strip()

    if not title or not body:
        return None
    return f"## {title}\n\n{body}"


def _drop_trailing_slide_page_number(lines: list[str]) -> list[str]:
    if len(lines) >= 2 and SLIDE_PAGE_NUMBER_RE.match(lines[-1].strip()):
        return lines[:-1]
    return lines


def _strip_slide_title_prefix(body: str, title: str) -> str:
    prefix_end = _matching_prefix_end(body, title)
    if prefix_end is None:
        return body
    remainder = body[prefix_end:].lstrip()
    repeated_end = _matching_prefix_end(remainder, title)
    if repeated_end is not None:
        second_remainder = remainder[repeated_end:].lstrip()
        if second_remainder and second_remainder[0] not in {"的", "是", "要", "需", "会", "能", "中"}:
            return second_remainder
        return remainder
    if not remainder or remainder[0] in {"的", "是", "要", "需", "会", "能", "中"}:
        return body
    return remainder


def _matching_prefix_end(text: str, title: str) -> int | None:
    target = re.sub(r"\s+", "", title)
    if not target:
        return None
    compact = ""
    for idx, char in enumerate(text):
        if char.isspace():
            continue
        compact += char
        if compact == target:
            return idx + 1
        if not target.startswith(compact):
            return None
    return None


def _is_translator_marketing_back_matter(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    if "译后记" not in compact and "本译本仅供" not in compact:
        return False
    hits = sum(1 for term in TRANSLATOR_BACK_MATTER_TERMS if term.replace(" ", "") in compact)
    return hits >= 3


def _render_topic_notes(kept_blocks: list[dict], vault_dir: Path) -> tuple[list[dict], list[dict]]:
    sections: list[dict] = []
    current: dict | None = None
    for block in kept_blocks:
        text = _renderable_text(block)
        if not text:
            continue
        if block.get("type") == "section_heading":
            if current and current["blocks"]:
                sections.append(current)
            title = _heading_title(text)
            current = {"title": title, "blocks": [block]}
            continue
        if current is None:
            current = {"title": "未分组知识", "blocks": []}
        current["blocks"].append(block)
    if current and current["blocks"]:
        sections.append(current)

    note_entries: list[dict] = []
    source_map: list[dict] = []
    counters = {"认知": 0, "方法": 0, "案例": 0}
    for section in sections:
        title = section["title"]
        category = _category_for_title(title)
        counters[category] += 1
        filename = f"{counters[category]:03d}-{_safe_filename(title)}.md"
        note_path = vault_dir / category / filename
        rel_note = f"{category}/{filename}"
        content = "\n".join([
            "---",
            f'title: "{_yaml_safe(title)}"',
            f'category: "{category}"',
            "kbprep_profile: curated_obsidian_kb",
            "---",
            "",
            _join_blocks(section["blocks"]),
            "",
        ])
        note_path.write_text(content, encoding="utf-8")
        note_entries.append({"title": title, "category": category, "path": rel_note})
        for block in section["blocks"]:
            source_map.append({
                "block_id": block.get("block_id"),
                "type": block.get("type"),
                "status": block.get("status"),
                "note": rel_note,
                "heading": title,
            })
    return note_entries, source_map


def _render_index(
    vault_dir: Path,
    source_title: str,
    note_entries: list[dict],
    kept_blocks: list[dict],
    discarded_blocks: list[dict],
    review_blocks: list[dict],
) -> None:
    lines = [
        "---",
        f'title: "{_yaml_safe(source_title)}"',
        "kbprep_profile: curated_obsidian_kb",
        "---",
        "",
        f"# {source_title}",
        "",
        "## 入口",
        "",
        "- [[01-完整正文]]",
        "- [[_audit/cleaning-report|清洗报告]]",
        "- [[_audit/review_needed|待复核内容]]",
        "",
        "## 统计",
        "",
        f"- 保留块：{len(kept_blocks)}",
        f"- 删除块：{len(discarded_blocks)}",
        f"- 待复核块：{len(review_blocks)}",
        "",
    ]
    for category in ["认知", "方法", "案例"]:
        entries = [entry for entry in note_entries if entry["category"] == category]
        if not entries:
            continue
        lines.extend([f"## {category}", ""])
        for entry in entries:
            link = entry["path"].removesuffix(".md")
            lines.append(f"- [[{link}|{entry['title']}]]")
        lines.append("")
    (vault_dir / "00-索引.md").write_text("\n".join(lines), encoding="utf-8")


def _render_audit_file(path: Path, blocks: list[dict]) -> None:
    lines: list[str] = []
    for block in blocks:
        lines.append(_block_meta_comment(block, include_reason=True))
        text = (block.get("text") or "").strip()
        if text:
            lines.append(text)
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _render_cleaning_report(
    path: Path,
    source_title: str,
    kept_blocks: list[dict],
    discarded_blocks: list[dict],
    review_blocks: list[dict],
    note_entries: list[dict],
) -> None:
    type_counts: dict[str, int] = {}
    for block in discarded_blocks:
        block_type = str(block.get("type") or "unknown")
        type_counts[block_type] = type_counts.get(block_type, 0) + 1
    lines = [
        f"# {source_title} 清洗报告",
        "",
        "## 输出原则",
        "",
        "- 正文段落不改写、不总结、不合并。",
        "- 作者简介、身份包装、广告和图片类内容从正文剥离。",
        "- 被删除或待复核内容保留在 `_audit` 中，可追溯恢复。",
        "",
        "## 统计",
        "",
        f"- 保留块：{len(kept_blocks)}",
        f"- 删除块：{len(discarded_blocks)}",
        f"- 待复核块：{len(review_blocks)}",
        f"- 主题笔记：{len(note_entries)}",
        "",
        "## 删除类型",
        "",
    ]
    if type_counts:
        for block_type, count in sorted(type_counts.items()):
            lines.append(f"- {block_type}: {count}")
    else:
        lines.append("- 无")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _category_for_title(title: str) -> str:
    if any(term in title for term in METHOD_TERMS):
        return "方法"
    if any(term in title for term in COGNITION_TERMS):
        return "认知"
    if any(term in title for term in CASE_TERMS):
        return "案例"
    return "案例"


def _heading_title(text: str) -> str:
    title = re.sub(r"^#{1,6}\s*", "", text.strip()).strip()
    title = _strip_author_prefix(title)
    title = _strip_brand_prefix(title)
    return title or "未命名知识"


def _is_packaging_heading(text: str) -> bool:
    title = _heading_title(text)
    return _is_packaging_heading_title(title)


def _is_packaging_heading_title(title: str) -> bool:
    if any(term in title for term in PACKAGING_HEADING_TERMS):
        return True
    if re.fullmatch(r"(?:生财|生财有术)?\s*AI\s*宝典", title, re.IGNORECASE):
        return True
    if "上线" in title and "宝典" in title:
        return True
    return False


def _is_noise_heading(text: str) -> bool:
    title = _heading_title(text)
    if len(title) <= 2 and not re.search(r"[A-Za-z0-9]", title):
        return True
    return False


def _is_direct_packaging_context(block: dict) -> bool:
    if block.get("type") == "section_heading":
        return False
    heading_path = block.get("heading_path") or []
    if not heading_path:
        return False
    last_heading = str(heading_path[-1])
    return _is_packaging_heading_title(_strip_brand_prefix(_strip_author_prefix(last_heading)))


def _safe_filename(title: str) -> str:
    clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", title).strip(" .-_")
    clean = re.sub(r"\s+", " ", clean)
    if len(clean) > 60:
        clean = clean[:60].rstrip()
    return clean or "未命名知识"


def _yaml_safe(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _is_empty_heading(text: str) -> bool:
    return bool(EMPTY_HEADING_RE.match(text.strip()))


def _is_author_intro(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    if len(compact) > 240:
        return False
    if any(term in text for term in AUTHOR_BIO_TERMS):
        return True
    role_hits = sum(1 for term in BIO_ROLE_TERMS if term in text)
    if role_hits >= 2 and not _has_strong_knowledge_signal(text):
        return True
    return False


def _is_author_identity_card(blocks: list[dict], index: int, text: str) -> bool:
    """Drop short byline/profile cards that sit between a title and the body.

    Standalone author cards are layout metadata, not body knowledge. The
    location check prevents deleting author/case context from normal paragraphs.
    """
    if not _is_author_card_line(text):
        return False
    return _is_in_author_card_window(blocks, index)


def _is_visual_chapter_separator(text: str) -> bool:
    clean = re.sub(r"\s+", " ", text.strip())
    if len(clean) > 80:
        return False
    return bool(VISUAL_CHAPTER_SEPARATOR_RE.fullmatch(clean))


def _is_front_matter_social_profile(blocks: list[dict], index: int, text: str) -> bool:
    """Drop top-of-document presenter/profile link strips, not body case context."""
    if "\n" in text or len(text) > 300:
        return False
    if _has_strong_knowledge_signal(text):
        return False
    if any(term in text for term in PROVENANCE_TERMS):
        return False

    # Only apply before the first real body section; author mentions inside a
    # case or method paragraph must stay because they can carry source context.
    for previous in blocks[:index]:
        previous_text = previous.get("text", "").strip()
        if previous.get("status") != "keep" or not previous_text:
            continue
        if previous.get("type") == "section_heading" and previous_text.startswith("## "):
            return False
    if index > 12:
        return False

    markdown_links = len(re.findall(r"\[[^\]]+\]\([^)]+\)", text))
    has_social_platform = any(term in text for term in SOCIAL_PROFILE_PLATFORMS)
    has_profile_label = any(re.search(rf"(^|\s){re.escape(term)}\s*[：:]", text) for term in SOCIAL_PROFILE_LABELS)
    return has_profile_label and (markdown_links >= 1 or has_social_platform)


def _is_author_card_line(text: str) -> bool:
    if "\n" in text or _is_toc_like(text):
        return False
    clean = _strip_heading_marks(text)
    compact = re.sub(r"\s+", "", clean)
    if not compact or len(compact) > 90:
        return False
    if AUTHOR_HANDLE_RE.fullmatch(compact):
        return True
    if any(term in clean for term in BIO_ROLE_TERMS):
        return not any(term in clean for term in ["方法", "步骤", "流程", "如何", "怎么", "为什么", "案例"])
    if any(term in clean for term in AUTHOR_CREDENTIAL_TERMS):
        return not re.match(r"^\s*(?:\d+[\.、）)]|第[一二三四五六七八九十]+)", clean)
    return False


def _is_in_author_card_window(blocks: list[dict], index: int) -> bool:
    saw_card = False
    cursor = index - 1
    while cursor >= 0 and index - cursor <= 5:
        previous = blocks[cursor]
        previous_text = previous.get("text", "").strip()
        if not previous_text or previous.get("status") == "discard":
            cursor -= 1
            continue
        if previous.get("type") == "section_heading":
            return True
        if _is_author_card_line(previous_text):
            saw_card = True
            cursor -= 1
            continue
        break
    return saw_card


def _strip_heading_marks(text: str) -> str:
    return re.sub(r"^#{1,6}\s*", "", text.strip()).strip()


def _is_layout_table_artifact(text: str) -> bool:
    if not text.lstrip().startswith("|"):
        return False
    empty_cells = len(re.findall(r"\|\s*(?=\|)", text))
    rows = [line for line in text.splitlines() if line.strip().startswith("|")]
    if empty_cells >= 4 and any(term in text for term in LAYOUT_TABLE_TERMS):
        return True
    if len(rows) <= 5 and empty_cells >= 3 and re.search(r"\b\d{1,2}:\d{2}\b", text):
        return True
    return False


def _is_brand_program_packaging(text: str) -> bool:
    return any(term in text for term in BRAND_PROGRAM_PACKAGING_TERMS)


def _drop_toc_windows(blocks: list[dict]) -> None:
    """Drop table-of-contents text plus the small heading window around it."""
    for index, block in enumerate(blocks):
        if block.get("status") != "keep":
            continue
        if not _is_toc_like(block.get("text", "")):
            continue
        _discard(block, "toc", "drop_table_of_contents_for_text_kb", 0.90)

        dropped = 0
        cursor = index - 1
        while cursor >= 0 and dropped < 3:
            previous = blocks[cursor]
            if previous.get("status") == "discard":
                cursor -= 1
                continue
            if previous.get("status") == "keep" and previous.get("type") == "section_heading":
                _discard(previous, "toc_heading", "drop_table_of_contents_heading_for_text_kb", 0.88)
                dropped += 1
                cursor -= 1
                continue
            break


def _is_toc_like(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        return False
    toc_lines = 0
    for line in lines:
        if len(line) > 120:
            continue
        if re.search(r"[：:].{2,}\s+\d{1,4}$", line):
            toc_lines += 1
        elif re.search(r".{4,}\s{2,}\d{1,4}$", line):
            toc_lines += 1
    return toc_lines >= 2 and toc_lines / len(lines) >= 0.5


def _has_strong_knowledge_signal(text: str) -> bool:
    if re.search(r"^\s*\d+[\.\)\uff09、]", text, re.MULTILINE):
        return True
    if any(term in text for term in KNOWLEDGE_TERMS):
        return True
    if re.search(r"[A-Za-z_]+=\S+", text):
        return True
    return False


def _discard(block: dict, block_type: str, reason: str, confidence: float) -> None:
    block["status"] = "discard"
    block["type"] = block_type
    block["reason"] = reason
    block["confidence"] = confidence
    block["protected"] = False
    _append_tag(block, reason)


def _append_tag(block: dict, tag: str) -> None:
    tags = block.setdefault("risk_tags", [])
    if tag not in tags:
        tags.append(tag)
