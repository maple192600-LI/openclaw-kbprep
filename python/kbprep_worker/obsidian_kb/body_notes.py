"""Body-note rendering for Obsidian knowledge-base output."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from ..fs_safety import safe_rmtree
from ..render_outputs import _block_meta_comment
from .context import ObsidianContext, context_for_template
from .frontmatter import _yaml_safe
from .links import _safe_filename
from .signals import IMAGE_TYPES, _is_internal_page_marker, _is_knowledge_diagram
from .titles import _heading_title, complete_body_filename


def render_obsidian_vault(
    blocks: list[dict],
    run_dir: str,
    source_title: str,
    source_hash: str,
    run_id: str,
    profile: str = "obsidian_kb",
    template_name: str = "obsidian_generic",
) -> None:
    """Render a text-first Obsidian wiki folder under run_dir/obsidian."""
    ctx = context_for_template(template_name)
    run_p = Path(run_dir)
    vault_dir = run_p / "obsidian"
    if vault_dir.exists():
        safe_rmtree(vault_dir, root=run_p)

    audit_dir = vault_dir / "_audit"
    for subdir in [*ctx.categories, "_audit", "images"]:
        (vault_dir / subdir).mkdir(parents=True, exist_ok=True)

    source_images = run_p / "images"
    vault_images = vault_dir / "images"
    if source_images.exists():
        safe_rmtree(vault_images, root=vault_dir)
        shutil.copytree(source_images, vault_images)

    kept_blocks = [b for b in blocks if b.get("status") == "keep" and _renderable_text(b)]
    review_blocks = [b for b in blocks if b.get("status") == "review"]
    discarded_blocks = [b for b in blocks if b.get("status") == "discard"]

    complete_body = _join_blocks(kept_blocks)
    complete_filename = complete_body_filename(source_title, ctx=ctx)
    (vault_dir / complete_filename).write_text(
        "\n".join([
            "---",
            f'title: "{_yaml_safe(source_title)}"',
            f"kbprep_profile: {profile}",
            f'source_sha256: "{source_hash}"',
            f'run_id: "{run_id}"',
            "---",
            "",
            complete_body,
            "",
        ]),
        encoding="utf-8",
    )

    note_entries, source_map = _render_topic_notes(kept_blocks, vault_dir, profile, ctx)
    _render_index(vault_dir, source_title, complete_filename, note_entries, kept_blocks, discarded_blocks, review_blocks, profile, ctx)
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
    _copy_run_evidence_to_obsidian_audit(run_p, audit_dir)


def _renderable_text(block: dict) -> str:
    text = (block.get("curated_text") or block.get("text") or "").strip()
    if not text:
        return ""
    if _is_internal_page_marker(text):
        return ""
    if block.get("type") in IMAGE_TYPES and not _is_knowledge_diagram(block):
        return ""
    return text


def _join_blocks(blocks: list[dict]) -> str:
    return "\n\n".join(_renderable_text(block) for block in blocks if _renderable_text(block))


def _copy_run_evidence_to_obsidian_audit(run_dir: Path, audit_dir: Path) -> None:
    for name in [
        "quality_report.json",
        "conversion_report.json",
        "diagnosis_report.json",
        "run_metadata.json",
        "source_conversion_integrity.json",
        "audit.md",
    ]:
        source = run_dir / name
        if source.exists():
            shutil.copy2(source, audit_dir / name)
    source_gate_dir = run_dir / "quality_gates"
    target_gate_dir = audit_dir / "quality_gates"
    if source_gate_dir.exists():
        if target_gate_dir.exists():
            safe_rmtree(target_gate_dir, root=audit_dir)
        shutil.copytree(source_gate_dir, target_gate_dir)


def _render_topic_notes(
    kept_blocks: list[dict],
    vault_dir: Path,
    profile: str,
    ctx: ObsidianContext,
) -> tuple[list[dict], list[dict]]:
    sections: list[dict] = []
    current: dict | None = None
    for block in kept_blocks:
        text = _renderable_text(block)
        if not text:
            continue
        if block.get("type") == "section_heading":
            if current and current["blocks"]:
                sections.append(current)
            title = _heading_title(text, ctx)
            current = {"title": title, "blocks": [block]}
            continue
        if current is None:
            current = {"title": "未分组知识", "blocks": []}
        current["blocks"].append(block)
    if current and current["blocks"]:
        sections.append(current)

    note_entries: list[dict] = []
    source_map: list[dict] = []
    counters = {category: 0 for category in ctx.categories}
    for section in sections:
        title = section["title"]
        category = _category_for_title(title, ctx)
        counters[category] += 1
        filename = f"{counters[category]:03d}-{_safe_filename(title)}.md"
        note_path = vault_dir / category / filename
        rel_note = f"{category}/{filename}"
        content = "\n".join([
            "---",
            f'title: "{_yaml_safe(title)}"',
            f'category: "{category}"',
            f"kbprep_profile: {profile}",
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
    complete_filename: str,
    note_entries: list[dict],
    kept_blocks: list[dict],
    discarded_blocks: list[dict],
    review_blocks: list[dict],
    profile: str,
    ctx: ObsidianContext,
) -> None:
    complete_link = complete_filename.removesuffix(".md")
    lines = [
        "---",
        f'title: "{_yaml_safe(source_title)}"',
        f"kbprep_profile: {profile}",
        "---",
        "",
        f"# {source_title}",
        "",
        "## 入口",
        "",
        f"- [[{complete_link}|完整正文]]",
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
    for category in ctx.categories:
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


def _category_for_title(title: str, ctx: ObsidianContext) -> str:
    if any(term in title for term in ctx.method_terms):
        return ctx.method_category
    if any(term in title for term in ctx.cognition_terms):
        return ctx.cognition_category
    if any(term in title for term in ctx.case_terms):
        return ctx.case_category
    return ctx.default_category
