"""Lightweight EPUB XHTML extraction."""

from __future__ import annotations

import posixpath
import re
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote
from xml.etree import ElementTree as ET


def analyze_epub(input_path: str) -> dict:
    markdown, warnings, spine_count, _image_assets = extract_epub_markdown(Path(input_path))
    text = re.sub(r"\s+", " ", markdown).strip()
    return {
        "page_count": spine_count,
        "chapter_count": spine_count,
        "total_text_length": len(text),
        "text_layer_health": "needs_conversion",
        "needs_ocr": False,
        "recommended_pipeline": "epub_xhtml",
        "conversion_strategy": "epub_xhtml",
        "warnings": warnings,
    }


def convert_epub(input_path: Path, output_path: Path, run_dir: Path | None = None) -> tuple[dict, list[str]]:
    markdown, warnings, _spine_count, image_assets = extract_epub_markdown(input_path, run_dir)
    if not markdown.strip():
        raise ValueError(f"{input_path.name} did not contain extractable EPUB XHTML text.")
    output_path.write_text(markdown.rstrip() + "\n", encoding="utf-8")
    return {
        "source_md_path": str(output_path),
        "content_list_path": None,
        "content_list_v2_path": None,
        "middle_json_path": None,
        "assets_dir": None,
        "converter": "epub_xhtml",
        "epub_image_assets": {
            "copied_count": len(image_assets),
            "copied": image_assets[:50],
        },
        "warnings": warnings,
    }, warnings


def extract_epub_markdown(input_path: Path, run_dir: Path | None = None) -> tuple[str, list[str], int, list[str]]:
    warnings: list[str] = []
    image_assets: list[str] = []
    if not zipfile.is_zipfile(input_path):
        raise ValueError(f"{input_path.name} is not a valid EPUB ZIP container.")

    with zipfile.ZipFile(input_path) as zf:
        rootfile = _find_rootfile(zf)
        opf_dir = posixpath.dirname(rootfile)
        spine_paths = _spine_xhtml_paths(zf, rootfile)
        if not spine_paths:
            warnings.append("W_EPUB_NO_SPINE: EPUB spine missing; using sorted XHTML/HTML files.")
            spine_paths = sorted(
                name for name in zf.namelist()
                if name.lower().endswith((".xhtml", ".html", ".htm"))
            )

        chapters: list[str] = []
        for href in spine_paths:
            path = href if "/" in href else posixpath.normpath(posixpath.join(opf_dir, href))
            if path not in zf.namelist():
                warnings.append(f"W_EPUB_MISSING_ITEM: {path}")
                continue
            html = zf.read(path).decode("utf-8", errors="replace")
            md = html_to_markdown(html, base_path=path, zf=zf, run_dir=run_dir, image_assets=image_assets)
            if md:
                chapters.append(md)

    markdown = "\n\n".join(chapters).strip()
    return markdown + ("\n" if markdown else ""), warnings, len(chapters), image_assets


def _find_rootfile(zf: zipfile.ZipFile) -> str:
    try:
        container = zf.read("META-INF/container.xml")
        root = ET.fromstring(container)
        for elem in root.iter():
            full_path = elem.attrib.get("full-path")
            if full_path:
                return full_path
    except Exception:
        pass
    candidates = [name for name in zf.namelist() if name.lower().endswith(".opf")]
    if not candidates:
        raise ValueError("EPUB package document (.opf) not found.")
    return candidates[0]


def _spine_xhtml_paths(zf: zipfile.ZipFile, rootfile: str) -> list[str]:
    opf = ET.fromstring(zf.read(rootfile))
    manifest: dict[str, str] = {}
    spine_ids: list[str] = []
    for elem in opf.iter():
        tag = elem.tag.rsplit("}", 1)[-1]
        if tag == "item":
            item_id = elem.attrib.get("id")
            href = elem.attrib.get("href")
            media_type = elem.attrib.get("media-type", "")
            if item_id and href and media_type in {"application/xhtml+xml", "text/html"}:
                manifest[item_id] = href
        elif tag == "itemref":
            idref = elem.attrib.get("idref")
            if idref:
                spine_ids.append(idref)
    return [manifest[idref] for idref in spine_ids if idref in manifest]


def html_to_markdown(
    html: str,
    base_path: str = "",
    zf: zipfile.ZipFile | None = None,
    run_dir: Path | None = None,
    image_assets: list[str] | None = None,
) -> str:
    parser = _EpubHtmlParser(base_path=base_path, zf=zf, run_dir=run_dir, image_assets=image_assets)
    parser.feed(html)
    parser.close()
    return parser.markdown()


class _EpubHtmlParser(HTMLParser):
    def __init__(
        self,
        base_path: str = "",
        zf: zipfile.ZipFile | None = None,
        run_dir: Path | None = None,
        image_assets: list[str] | None = None,
    ) -> None:
        super().__init__(convert_charrefs=True)
        self.lines: list[str] = []
        self.current: list[str] = []
        self.skip_depth = 0
        self.heading_level: int | None = None
        self.in_li = False
        self.link_stack: list[tuple[str, int]] = []
        self.base_path = base_path
        self.zf = zf
        self.run_dir = run_dir
        self.image_assets = image_assets if image_assets is not None else []

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        attrs_dict = {key.lower(): value for key, value in attrs if value is not None}
        if tag in {"script", "style", "nav", "footer", "header"}:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag in {"p", "div", "section", "article"}:
            self._flush()
        elif tag in {"br"}:
            self.current.append("\n")
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._flush()
            self.heading_level = int(tag[1])
        elif tag == "li":
            self._flush()
            self.in_li = True
        elif tag == "tr":
            self._flush()
        elif tag in {"td", "th"}:
            if self.current:
                self.current.append(" | ")
        elif tag == "a":
            href = (attrs_dict.get("href") or "").strip()
            if href:
                self.link_stack.append((href, len(self.current)))
        elif tag == "img":
            src = (attrs_dict.get("src") or "").strip()
            if src:
                alt = (attrs_dict.get("alt") or attrs_dict.get("title") or "").strip()
                self.current.append(f"![{alt}]({self._image_src(src)})")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self.skip_depth:
            if tag in {"script", "style", "nav", "footer", "header"}:
                self.skip_depth = max(0, self.skip_depth - 1)
            return
        if tag in {"p", "div", "section", "article", "tr"}:
            self._flush()
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._flush(heading_level=self.heading_level)
            self.heading_level = None
        elif tag == "li":
            self._flush(list_item=True)
            self.in_li = False
        elif tag == "a":
            self._close_link()

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        text = re.sub(r"\s+", " ", data)
        if text.strip():
            self.current.append(text)

    def _close_link(self) -> None:
        if not self.link_stack:
            return
        href, start = self.link_stack.pop()
        if start > len(self.current):
            return
        label = "".join(self.current[start:]).strip() or href
        del self.current[start:]
        self.current.append(f"[{label}]({href})")

    def _image_src(self, src: str) -> str:
        if self.zf is None or self.run_dir is None or _is_external(src):
            return src
        clean_src = unquote(src.strip().split("#", 1)[0].split("?", 1)[0])
        if not clean_src:
            return src
        source_name = posixpath.normpath(posixpath.join(posixpath.dirname(self.base_path), clean_src))
        if source_name not in self.zf.namelist():
            return src
        suffix = Path(source_name).suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp", ".gif"}:
            return src

        rel_output = Path("epub") / Path(*source_name.split("/"))
        dst = self.run_dir / "images" / rel_output
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(self.zf.read(source_name))
        markdown_src = "images/" + rel_output.as_posix()
        if markdown_src not in self.image_assets:
            self.image_assets.append(markdown_src)
        return markdown_src

    def _flush(self, heading_level: int | None = None, list_item: bool = False) -> None:
        text = "".join(self.current).strip()
        self.current = []
        if not text:
            return
        if heading_level:
            self.lines.append(f"{'#' * heading_level} {text}")
        elif list_item:
            self.lines.append(f"- {text}")
        else:
            self.lines.append(text)

    def markdown(self) -> str:
        self._flush()
        cleaned: list[str] = []
        for line in self.lines:
            if line and (not cleaned or cleaned[-1] != line):
                cleaned.append(line)
        return "\n\n".join(cleaned).strip()


def _is_external(src: str) -> bool:
    return bool(re.match(r"^(?:https?:)?//|^data:|^mailto:|^#", src, re.IGNORECASE))
