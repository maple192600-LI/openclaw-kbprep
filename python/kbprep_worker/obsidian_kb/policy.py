"""Curated Obsidian block policy."""

from __future__ import annotations

from ..quality.thresholds import OBSIDIAN_CONFIDENCE
from .context import context_for_template
from .signals import (
    IMAGE_TYPES,
    _append_tag,
    _curated_slide_chapter_body,
    _discard,
    _drop_toc_windows,
    _has_strong_knowledge_signal,
    _is_author_identity_card,
    _is_author_intro,
    _is_brand_program_packaging,
    _is_direct_packaging_context,
    _is_empty_heading,
    _is_front_matter_social_profile,
    _is_internal_page_marker,
    _is_knowledge_diagram,
    _is_layout_table_artifact,
    _is_noise_heading,
    _is_packaging_heading,
    _is_translator_marketing_back_matter,
    _is_visual_chapter_separator,
    _slide_chapter_divider_title,
)
from .titles import sanitize_heading_text


def apply_curated_obsidian_policy(blocks: list[dict], template_name: str = "obsidian_generic") -> list[dict]:
    """Apply text-first Obsidian curation metadata to existing blocks.

    The policy is intentionally conservative around useful knowledge. It only
    discards identity/bio noise and image-only artifacts. Content with concrete
    method or case signals is kept, and ambiguous identity-like text goes to
    review instead of being silently removed.
    """
    ctx = context_for_template(template_name)
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
                block["confidence"] = max(float(block.get("confidence") or 0), OBSIDIAN_CONFIDENCE["keep_html_diagram"])
                _append_tag(block, "html_diagram")
                continue
            _discard(block, "image_artifact", "drop_image_for_text_kb", OBSIDIAN_CONFIDENCE["drop_image_artifact"])
            continue

        if block.get("status") != "keep":
            continue

        if _is_internal_page_marker(text):
            _discard(block, "page_marker", "drop_internal_page_marker_for_readable_kb", OBSIDIAN_CONFIDENCE["drop_internal_page_marker"])
            continue

        if slide_chapter_title:
            _discard(block, "slide_chapter_divider", "drop_standalone_slide_chapter_divider_for_kb", OBSIDIAN_CONFIDENCE["drop_slide_chapter_divider"])
            continue

        curated_chapter_text = _curated_slide_chapter_body(text, current_slide_chapter_title)
        if curated_chapter_text:
            block["curated_text"] = curated_chapter_text
            _append_tag(block, "slide_chapter_heading_normalized")
            continue

        if _is_visual_chapter_separator(text):
            _discard(block, "layout_separator", "drop_visual_chapter_separator_for_obsidian_kb", OBSIDIAN_CONFIDENCE["drop_layout_separator"])
            continue

        if _is_translator_marketing_back_matter(text, ctx):
            _discard(block, "translator_marketing_back_matter", "drop_translator_social_back_matter_for_kb", OBSIDIAN_CONFIDENCE["drop_translator_back_matter"])
            continue

        if _is_front_matter_social_profile(blocks, index, text, ctx):
            _discard(block, "author_profile_links", "drop_front_matter_author_or_social_profile_for_kb", OBSIDIAN_CONFIDENCE["drop_author_profile_links"])
            continue

        if _is_author_identity_card(blocks, index, text, ctx):
            _discard(block, "author_identity", "drop_author_identity_card_for_text_kb", OBSIDIAN_CONFIDENCE["drop_author_identity_card"])
            continue

        if block.get("type") == "table" and _is_layout_table_artifact(text, ctx):
            _discard(block, "layout_table_artifact", "drop_layout_table_for_text_kb", OBSIDIAN_CONFIDENCE["drop_layout_table"])
            continue

        if _is_direct_packaging_context(block, ctx):
            _discard(block, "marketing_wrapper", "drop_packaging_context_for_text_kb", OBSIDIAN_CONFIDENCE["drop_packaging_context"])
            continue

        if _is_brand_program_packaging(text, ctx):
            _discard(block, "marketing_wrapper", "drop_brand_program_packaging_for_text_kb", OBSIDIAN_CONFIDENCE["drop_brand_program_packaging"])
            continue

        if _is_empty_heading(text):
            _discard(block, "empty_heading", "empty heading after source cleanup", OBSIDIAN_CONFIDENCE["drop_empty_heading"])
            continue

        if block.get("type") == "section_heading":
            if _is_packaging_heading(text, ctx) or _is_noise_heading(text, ctx):
                _discard(block, "marketing_wrapper", "drop_packaging_heading_for_text_kb", OBSIDIAN_CONFIDENCE["drop_packaging_heading"])
                continue
            sanitized = sanitize_heading_text(text, ctx=ctx)
            if sanitized != text:
                block["curated_text"] = sanitized
                _append_tag(block, "heading_author_prefix_removed")
            continue

        if _is_author_intro(text, ctx):
            if _has_strong_knowledge_signal(text, ctx):
                block["status"] = "review"
                block["type"] = "author_intro_review"
                block["reason"] = "identity-heavy text also contains possible knowledge signals"
                block["confidence"] = OBSIDIAN_CONFIDENCE["author_intro_review"]
                _append_tag(block, "possible_author_intro")
            else:
                _discard(block, "author_intro", "author bio or identity wrapper unrelated to knowledge body", OBSIDIAN_CONFIDENCE["drop_author_intro"])
            continue

    _drop_toc_windows(blocks)
    return blocks
