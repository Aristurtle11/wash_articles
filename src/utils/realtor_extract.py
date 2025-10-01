"""Realtor-specific content extraction helpers."""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
import http.cookiejar
from pathlib import Path
from typing import Any, Sequence

from bs4 import BeautifulSoup

from ..settings import load_default_headers


def extract_article_content(html: str, base_url: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    hero_entry: dict[str, Any] | None = None
    hero_node: dict[str, Any] | None = None
    next_script = soup.find("script", id="__NEXT_DATA__")
    if next_script and next_script.string:
        try:
            data = json.loads(next_script.string)
            page_props = data.get("props", {}).get("pageProps", {})
            post_data = page_props.get("post", {})
            hide_featured = post_data.get("hideFeaturedImageOnArticlePage")
            if isinstance(hide_featured, dict):
                hide_featured = hide_featured.get("hidefeaturedimage")
            hero_candidate = {} if hide_featured else post_data.get("featuredImage", {})
            if isinstance(hero_candidate, dict):
                hero_candidate = (
                    hero_candidate.get("node") if "node" in hero_candidate else hero_candidate
                )
            if isinstance(hero_candidate, dict):
                hero_node = hero_candidate
                hero_entry = _hero_entry(hero_candidate, base_url)
            blocks = (
                data.get("props", {}).get("pageProps", {}).get("post", {}).get("editorBlocks", [])
            )
            if isinstance(blocks, list) and blocks:
                return _extract_from_editor_blocks(blocks, base_url, hero=hero_node)
        except (json.JSONDecodeError, TypeError):
            pass

    return _extract_from_dom(soup, base_url, hero=hero_entry)


def render_content_to_text(content: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for entry in content:
        kind = entry.get("kind")
        if kind == "heading":
            lines.append(f"## {entry['text']}")
            lines.append("")
        elif kind == "paragraph":
            text = entry.get("text") or "(no text)"
            lines.append(text)
            lines.append("")
        elif kind == "image":
            sequence = entry.get("sequence")
            try:
                sequence_int = int(sequence)
            except (TypeError, ValueError):
                sequence_int = 0
            marker = f"{{{{[Image {sequence_int}]}}}}" if sequence_int else "{{[Image]}}"
            lines.append(marker)
            lines.append("")
        else:
            text = entry.get("text")
            if text:
                lines.append(text)
                lines.append("")
    return "\n".join(lines).strip() + "\n"


def _extract_from_dom(
    soup: BeautifulSoup,
    base_url: str,
    hero: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = []
    paragraph_counter = 0
    image_counter = 0
    if hero and hero.get("url"):
        image_counter = 1
        content.append({**hero, "sequence": image_counter})
    for node in soup.select(".core-paragraph, h2, h3, h4, figure"):
        if node.name in {"h2", "h3", "h4"}:
            classes = node.get("class", [])
            is_article_heading = any(
                cls in {"htWOzS"} or cls.startswith("core-heading") or cls == "wp-block-heading"
                for cls in classes
            )
            if not is_article_heading:
                continue
            heading_text = node.get_text(strip=True)
            if heading_text:
                content.append(
                    {
                        "kind": "heading",
                        "level": int(node.name[1]),
                        "text": heading_text,
                    }
                )
            continue

        if node.name == "figure":
            img = node.find("img")
            if not img:
                continue
            src = (img.get("src") or img.get("data-src") or "").strip()
            if not src:
                continue
            absolute = urllib.parse.urljoin(base_url, src)
            if not absolute:
                continue
            image_counter += 1
            content.append(
                {
                    "kind": "image",
                    "sequence": image_counter,
                    "url": absolute,
                    "alt": (img.get("alt") or "").strip(),
                    "caption": node.get_text(strip=True),
                    "credit": "",
                }
            )
            continue

        text = node.get_text(strip=True)
        if text:
            paragraph_counter += 1
            content.append(
                {
                    "kind": "paragraph",
                    "index": paragraph_counter,
                    "text": text,
                }
            )
    return content


def _hero_entry(hero_data: dict[str, Any], base_url: str) -> dict[str, Any] | None:
    source = str(hero_data.get("sourceUrl") or "").strip()
    if not source:
        return None
    absolute = urllib.parse.urljoin(base_url, source)
    if not absolute:
        return None
    alt_text = str(hero_data.get("altText") or "").strip()
    caption_html = hero_data.get("caption") or ""
    caption = _strip_html(str(caption_html))
    credit = str(hero_data.get("imageCredit") or "").strip()
    return {
        "kind": "image",
        "sequence": 1,
        "url": absolute,
        "alt": alt_text,
        "caption": caption,
        "credit": credit,
    }


def _extract_from_editor_blocks(
    blocks: Sequence[dict[str, Any]],
    base_url: str,
    hero: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = []
    paragraph_counter = 0
    image_counter = 0
    if hero:
        hero_entry = _hero_entry(hero, base_url)
        if hero_entry:
            content.append(hero_entry)
            image_counter = hero_entry["sequence"]
    for block in blocks:
        typename = block.get("__typename")
        if typename == "CoreHeading":
            attributes = block.get("attributes") or {}
            text = str(attributes.get("content") or "").strip()
            if not text:
                continue
            try:
                level = int(attributes.get("level", 2))
            except (TypeError, ValueError):
                level = 2
            content.append({"kind": "heading", "level": level, "text": text})
        elif typename == "CoreParagraph":
            rendered = block.get("renderedHtml") or ""
            block_soup = BeautifulSoup(rendered, "html.parser")
            text = block_soup.get_text(" ", strip=True)
            if not text:
                continue
            paragraph_counter += 1
            content.append(
                {
                    "kind": "paragraph",
                    "index": paragraph_counter,
                    "text": text,
                }
            )
        elif typename == "CoreImage":
            attributes = block.get("attributes") or {}
            src = str(attributes.get("src") or "").strip()
            if not src:
                continue
            absolute = urllib.parse.urljoin(base_url, src)
            if not absolute:
                continue
            image_counter += 1
            caption = str(attributes.get("caption") or "").strip()
            alt = str(attributes.get("alt") or "").strip()
            credit = block.get("imageCredit")
            image_credit = str(credit).strip() if isinstance(credit, str) else ""
            content.append(
                {
                    "kind": "image",
                    "sequence": image_counter,
                    "url": absolute,
                    "alt": alt,
                    "caption": caption,
                    "credit": image_credit,
                }
            )
    return content


def _strip_html(text: str) -> str:
    if not text:
        return ""
    soup = BeautifulSoup(text, "html.parser")
    return soup.get_text(" ", strip=True)


def download_images(
    image_entries: Sequence[dict[str, Any]],
    *,
    cookie_jar_path: str | os.PathLike[str],
    dest_dir: os.PathLike[str],
    timeout: float = 15.0,
) -> list[dict[str, Any]]:
    jar = http.cookiejar.MozillaCookieJar(str(cookie_jar_path))
    try:
        jar.load(ignore_discard=True, ignore_expires=True)
    except (FileNotFoundError, http.cookiejar.LoadError, OSError):
        pass

    dest_path = Path(dest_dir)
    dest_path.mkdir(parents=True, exist_ok=True)

    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    base_headers = load_default_headers()

    saved_by_url: dict[str, Path] = {}
    results: list[dict[str, Any]] = []
    counter = 0

    for entry in image_entries:
        try:
            sequence = int(entry.get("sequence", 0))
        except (TypeError, ValueError):
            sequence = 0
        url = str(entry.get("url") or "").strip()
        if not url or sequence <= 0:
            results.append({"sequence": sequence, "url": url, "path": None})
            continue
        if url in saved_by_url:
            results.append({"sequence": sequence, "url": url, "path": saved_by_url[url]})
            continue

        headers = base_headers.copy()
        jar_cookie = _cookie_header_from_jar(jar, url)
        if jar_cookie:
            headers["Cookie"] = jar_cookie

        request = urllib.request.Request(url=url, headers=headers)
        counter += 1
        filename = dest_path / f"image_{counter:03d}{_extension_from_url(url)}"

        with opener.open(request, timeout=timeout) as resp:
            data = resp.read()
        filename.write_bytes(data)

        saved_by_url[url] = filename
        results.append({"sequence": sequence, "url": url, "path": filename})

    try:
        jar.save(ignore_discard=True, ignore_expires=True)
    except OSError:
        pass

    return results


def _extension_from_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    _, ext = os.path.splitext(parsed.path)
    return ext if ext else ".bin"


def _cookie_header_from_jar(jar: http.cookiejar.CookieJar, url: str) -> str:
    request = urllib.request.Request(url)
    jar.add_cookie_header(request)
    return request.get_header("Cookie", "")
