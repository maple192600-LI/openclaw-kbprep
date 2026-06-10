from __future__ import annotations

import re
import shutil
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote

from ..supported_formats import IMAGE_EXTENSIONS


def _is_nonlocal_markdown_image(path_text: str) -> bool:
    return bool(re.match(r"^(?:https?:)?//|^data:|^mailto:|^#", path_text, re.IGNORECASE))


def _looks_like_image_reference(path_text: str) -> bool:
    clean = path_text.split("?", 1)[0].split("#", 1)[0]
    return Path(clean).suffix.lower() in IMAGE_EXTENSIONS


class _HTMLToMarkdownParser(HTMLParser):
    """Small stdlib HTML reader for saved pages and exported web notes."""

    BLOCK_TAGS = {"article", "main", "section", "p", "div", "blockquote", "tr"}
    SKIP_TAGS = {"script", "style", "svg", "noscript", "nav", "header", "footer"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lines: list[str] = []
        self.current: list[str] = []
        self.skip_depth = 0
        self.heading_level: int | None = None
        self.in_li = False
        self.link_stack: list[tuple[str, int]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attrs_dict = {key.lower(): value for key, value in attrs if value is not None}
        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._flush()
            self.heading_level = int(tag[1])
        elif tag == "li":
            self._flush()
            self.in_li = True
        elif tag == "br":
            self._flush()
        elif tag == "a":
            href = (attrs_dict.get("href") or "").strip()
            if href:
                self.link_stack.append((href, len(self.current)))
        elif tag == "img":
            src = (attrs_dict.get("src") or "").strip()
            if src:
                alt = (attrs_dict.get("alt") or attrs_dict.get("title") or "").strip()
                self.current.append(f"![{alt}]({src})")
        elif tag in self.BLOCK_TAGS:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1
            return
        if self.skip_depth:
            return
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._flush(heading_level=self.heading_level)
            self.heading_level = None
        elif tag == "li":
            self._flush(list_item=True)
            self.in_li = False
        elif tag == "a":
            self._close_link()
        elif tag in self.BLOCK_TAGS or tag in {"ul", "ol", "table"}:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        text = re.sub(r"\s+", " ", data).strip()
        if text:
            self.current.append(text)

    def _close_link(self) -> None:
        if not self.link_stack:
            return
        href, start = self.link_stack.pop()
        if start > len(self.current):
            return
        label = " ".join(self.current[start:]).strip() or href
        del self.current[start:]
        self.current.append(f"[{label}]({href})")

    def _flush(self, heading_level: int | None = None, list_item: bool = False) -> None:
        text = " ".join(self.current).strip()
        self.current = []
        if not text:
            return
        if heading_level:
            self.lines.append(f"{'#' * min(heading_level, 6)} {text}")
        elif list_item:
            self.lines.append(f"- {text}")
        else:
            self.lines.append(text)

    def markdown(self) -> str:
        self._flush(heading_level=self.heading_level, list_item=self.in_li)
        cleaned: list[str] = []
        previous = ""
        for line in self.lines:
            line = line.strip()
            if line and line != previous:
                cleaned.append(line)
                previous = line
        return "\n\n".join(cleaned).strip() + "\n"


def html_to_markdown(
    text: str,
    run_dir: Path | None = None,
    source_stem: str = "html",
    source_root: Path | None = None,
) -> str:
    rich = rich_html_to_markdown(text, run_dir=run_dir, source_stem=source_stem, source_root=source_root)
    if rich.strip():
        return rich
    parser = _HTMLToMarkdownParser()
    parser.feed(text)
    markdown = parser.markdown()
    return markdown if markdown.strip() else re.sub(r"<[^>]+>", "", text).strip() + "\n"


def rich_html_to_markdown(
    text: str,
    run_dir: Path | None = None,
    source_stem: str = "html",
    source_root: Path | None = None,
) -> str:
    """Convert readable HTML pages while preserving tables, cards, and SVG diagrams.

    Many saved course pages encode important knowledge as visual cards, tables,
    and inline SVG diagrams. The small stdlib fallback intentionally stays simple,
    but this richer path keeps the structure that makes those pages usable in
    Obsidian.
    """
    try:
        from bs4 import BeautifulSoup, NavigableString, Tag
    except Exception:
        return ""

    soup = BeautifulSoup(text, "lxml")
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "button"]):
        tag.decompose()

    body = soup.body or soup.find("main") or soup
    assets_dir = run_dir / "images" if run_dir else None
    svg_counter = 0

    def clean(value: str) -> str:
        return re.sub(r"\s+", " ", value or "").strip()

    page_title = clean(soup.title.get_text(" ", strip=True)) if soup.title else ""
    asset_stem = page_title or source_stem

    def inline(node) -> str:
        if isinstance(node, NavigableString):
            return clean(str(node))
        if not isinstance(node, Tag):
            return ""
        name = node.name.lower()
        if name in {"script", "style", "noscript", "svg"}:
            return ""
        if name == "br":
            return "  \n"
        if name in {"strong", "b"}:
            inner = clean(" ".join(inline(c) for c in node.children))
            return f"**{inner}**" if inner else ""
        if name in {"em", "i"}:
            inner = clean(" ".join(inline(c) for c in node.children))
            return f"*{inner}*" if inner else ""
        if name == "code":
            inner = node.get_text("", strip=True)
            return f"`{inner}`" if inner else ""
        if name == "a":
            href = clean(node.get("href", ""))
            label = clean(" ".join(inline(c) for c in node.children)) or clean(node.get_text(" ", strip=True)) or href
            return f"[{label}]({href})" if href else label
        if name == "img":
            alt = clean(node.get("alt") or node.get("title") or "")
            src = clean(node.get("src", ""))
            if not src:
                return alt
            if src.startswith("assets/logos/"):
                return alt
            rewritten = copy_html_image(src)
            return f"![{alt}]({rewritten or src})"
        return clean(" ".join(inline(c) for c in node.children))

    def table_to_md(table: Tag) -> str:
        rows: list[list[str]] = []
        for tr in table.find_all("tr"):
            cells = tr.find_all(["th", "td"], recursive=False)
            if cells:
                rows.append([clean(cell.get_text(" ", strip=True)).replace("|", "\\|") for cell in cells])
        if not rows:
            return ""
        width = max(len(row) for row in rows)
        rows = [row + [""] * (width - len(row)) for row in rows]
        header, body_rows = rows[0], rows[1:]
        lines = [
            "| " + " | ".join(header) + " |",
            "| " + " | ".join(["---"] * width) + " |",
        ]
        for row in body_rows:
            lines.append("| " + " | ".join(row) + " |")
        return "\n".join(lines)

    def copy_html_image(src: str) -> str | None:
        if not source_root or not assets_dir or _is_nonlocal_markdown_image(src):
            return None
        decoded = unquote(src).replace("\\", "/").split("?", 1)[0].split("#", 1)[0]
        if not _looks_like_image_reference(decoded):
            return None
        source_path = (source_root / decoded).resolve()
        try:
            rel = source_path.relative_to(source_root)
        except ValueError:
            return None
        if not source_path.is_file():
            return None
        safe_parts = [part for part in rel.parts if part not in {"", ".", ".."}]
        if not safe_parts:
            return None
        target_path = assets_dir / Path(*safe_parts)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if not target_path.exists():
            shutil.copy2(str(source_path), str(target_path))
        return "images/" + Path(*safe_parts).as_posix()

    def svg_to_md(svg: Tag) -> str:
        nonlocal svg_counter
        label = clean(svg.get("aria-label") or "")
        title = svg.find("title")
        desc = svg.find("desc")
        if not label and title:
            label = clean(title.get_text(" ", strip=True))
        if not label and desc:
            label = clean(desc.get_text(" ", strip=True))
        label = label or "HTML diagram"
        if not assets_dir:
            visible_text = clean(svg.get_text(" ", strip=True))
            return f"> [!info] {label}\n> {visible_text}" if visible_text else f"> [!info] {label}"
        svg_counter += 1
        assets_dir.mkdir(parents=True, exist_ok=True)
        safe_stem = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "-", asset_stem).strip(".-_") or "html"
        filename = f"{safe_stem}-diagram-{svg_counter:02d}.svg"
        svg_text = _standalone_svg_text(svg)
        (assets_dir / filename).write_text(svg_text, encoding="utf-8")
        return f"![{label}](images/{filename})"

    def block(node, depth: int = 0) -> list[str]:
        if isinstance(node, NavigableString):
            text_value = clean(str(node))
            return [text_value] if text_value else []
        if not isinstance(node, Tag):
            return []
        name = node.name.lower()
        if name in {"script", "style", "noscript", "nav", "header", "footer", "button"}:
            return []
        if name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            heading = inline(node)
            return [f"{'#' * int(name[1])} {heading}"] if heading else []
        if name in {"p", "blockquote"}:
            paragraph = inline(node)
            if not paragraph:
                return []
            if name == "blockquote" or "quote" in (node.get("class") or []):
                return ["> " + paragraph]
            return [paragraph]
        if name == "svg":
            return [svg_to_md(node)]
        if name == "table":
            table_md = table_to_md(node)
            return [table_md] if table_md else []
        if name in {"ul", "ol"}:
            lines: list[str] = []
            ordered = name == "ol"
            for idx, li in enumerate(node.find_all("li", recursive=False), start=1):
                li_text = inline(li)
                if li_text:
                    prefix = f"{idx}. " if ordered else "- "
                    lines.append(prefix + li_text)
            return ["\n".join(lines)] if lines else []
        if name == "li":
            li_text = inline(node)
            return [f"- {li_text}"] if li_text else []
        if name == "img":
            image = inline(node)
            return [image] if image else []
        if name in {"div", "main", "body", "html"}:
            classes = set(node.get("class") or [])
            child_lines: list[str] = []
            if "card" in classes or "case-card" in classes:
                title = None
                for heading_tag in ["h3", "h4"]:
                    found = node.find(heading_tag)
                    if found:
                        title = inline(found)
                        break
                if title:
                    child_lines.append(f"#### {title}")
            for child in node.children:
                if isinstance(child, Tag) and "card" in classes and child.name and child.name.lower() in {"h3", "h4"}:
                    continue
                child_lines.extend(block(child, depth + 1))
            return child_lines
        if name in {"span", "strong", "b", "em", "i", "a", "code"}:
            value = inline(node)
            return [value] if value else []
        fallback_lines: list[str] = []
        for child in node.children:
            fallback_lines.extend(block(child, depth + 1))
        return fallback_lines

    lines = block(body)
    cleaned: list[str] = []
    previous = ""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line == previous:
            continue
        cleaned.append(line)
        previous = line
    return "\n\n".join(cleaned).strip() + ("\n" if cleaned else "")


def _standalone_svg_text(svg) -> str:
    """Serialize an inline HTML SVG as a valid standalone SVG asset."""
    if "viewBox" not in svg.attrs and "viewbox" in svg.attrs:
        svg["viewBox"] = svg.attrs.pop("viewbox")

    view_box = str(svg.get("viewBox") or "").strip()
    view_box_numbers = _parse_svg_view_box(view_box)
    if view_box_numbers:
        _, _, width, height = view_box_numbers
        root_width = str(svg.get("width") or "").strip()
        root_height = str(svg.get("height") or "").strip()
        if not root_width or root_width.endswith("%"):
            svg["width"] = _format_svg_number(width)
        if not root_height or root_height.endswith("%"):
            svg["height"] = _format_svg_number(height)

    if "preserveAspectRatio" not in svg.attrs:
        svg["preserveAspectRatio"] = "xMidYMid meet"

    svg_text = str(svg)
    root_open = svg_text.split(">", 1)[0]
    if "<svg" in svg_text and "xmlns=" not in root_open:
        svg_text = svg_text.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"', 1)
    return svg_text


def _parse_svg_view_box(value: str) -> tuple[float, float, float, float] | None:
    parts = re.split(r"[\s,]+", value.strip())
    if len(parts) != 4:
        return None
    try:
        n0, n1, n2, n3 = (float(part) for part in parts)
    except ValueError:
        return None
    numbers = (n0, n1, n2, n3)
    if numbers[2] <= 0 or numbers[3] <= 0:
        return None
    return numbers


def _format_svg_number(value: float) -> str:
    return str(int(value)) if value.is_integer() else str(value)


def _escape_table_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()
