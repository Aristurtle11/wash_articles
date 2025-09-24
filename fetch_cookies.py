import gzip
import http.cookiejar
import io
import json
import os
import random
import time
import pathlib
import urllib.error
import urllib.parse
import urllib.request
import zlib
from typing import Any, Sequence

from bs4 import BeautifulSoup

HEADERS_TEMPLATE_FILE = "default_headers.template.json"

COOKIE_JAR_FILE = "cookies.txt"
HEADERS_FILE = "default_headers.json"
ASSET_DIR = pathlib.Path("asset")


def _decode_body(body: bytes, encoding: str) -> str:
    if not encoding:
        return body.decode(errors="replace")
    if encoding == "gzip":
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(body)) as gz:
                return gz.read().decode(errors="replace")
        except (OSError, EOFError) as exc:
            return f"<gzip decode failed: {exc}>"
    if encoding == "deflate":
        try:
            return zlib.decompress(body).decode(errors="replace")
        except zlib.error:
            return zlib.decompress(body, -zlib.MAX_WBITS).decode(errors="replace")
    if encoding == "br":
        try:
            import brotli  # type: ignore
        except ModuleNotFoundError:
            return "<brotli module missing; raw bytes omitted>"
        try:
            return brotli.decompress(body).decode(errors="replace")
        except brotli.error as exc:  # type: ignore[attr-defined]
            return f"<brotli decode failed: {exc}>"
    return f"<unsupported encoding {encoding}>"


def _load_headers_template() -> dict[str, str]:
    with open(HEADERS_TEMPLATE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        return {str(k): str(v) for k, v in data.items()}


def load_default_headers() -> dict[str, str]:
    if os.path.exists(HEADERS_FILE):
        try:
            with open(HEADERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {str(k): str(v) for k, v in data.items()}
        except (OSError, json.JSONDecodeError):
            pass
    try:
        headers = _load_headers_template()
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Unable to load header template from {HEADERS_TEMPLATE_FILE}."
        ) from exc
    save_default_headers(headers)
    return dict(headers)


def save_default_headers(headers: dict[str, str]) -> None:
    try:
        with open(HEADERS_FILE, "w", encoding="utf-8") as f:
            json.dump(headers, f, ensure_ascii=True, indent=2, sort_keys=True)
    except OSError:
        pass


def update_cookie_header_in_config(headers: dict[str, str], new_cookie_header: str) -> bool:
    if not new_cookie_header:
        return False
    current = headers.get("Cookie", "")
    if current == new_cookie_header:
        return False
    headers["Cookie"] = new_cookie_header
    save_default_headers(headers)
    return True


def _cookie_header_from_jar_for_url(jar: http.cookiejar.CookieJar, url: str) -> str:
    # Let CookieJar compute the correct Cookie header for the URL.
    req = urllib.request.Request(url)
    jar.add_cookie_header(req)
    return req.get_header("Cookie", "")

def fetch_cookies(
    url: str,
    headers: dict[str, str] | None = None,
    *,
    min_delay: float = 0.0,
    max_delay: float = 0.0,
    max_attempts: int = 3,
    backoff_factor: float = 1.5,
) -> tuple[http.cookiejar.CookieJar, dict[str, str]]:
    # Persist cookies across runs
    jar = http.cookiejar.MozillaCookieJar(COOKIE_JAR_FILE)
    if os.path.exists(COOKIE_JAR_FILE):
        try:
            jar.load(ignore_discard=True, ignore_expires=True)
        except (OSError, http.cookiejar.LoadError):
            pass
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    request_headers = load_default_headers()
    if headers:
        request_headers.update(headers)
    # Prefer cookies from the persisted jar for this URL
    try:
        jar_cookie_header = _cookie_header_from_jar_for_url(jar, url)
    except Exception:
        jar_cookie_header = ""
    if jar_cookie_header:
        request_headers["Cookie"] = jar_cookie_header
    request = urllib.request.Request(url=url, headers=request_headers)
    delay = random.uniform(min_delay, max_delay) if max_delay > 0 else 0.0
    attempt = 0
    while True:
        try:
            if attempt == 0 and delay > 0:
                time.sleep(delay)
            with opener.open(request, timeout=10) as response:
                body = response.read()
                encoding = response.headers.get("Content-Encoding", "").lower()
                decoded = _decode_body(body, encoding)
                print("Response snippet:", json.dumps(decoded[:200]))
            break
        except urllib.error.HTTPError as exc:
            attempt += 1
            if exc.code != 429 or attempt >= max_attempts:
                raise
            retry_after = exc.headers.get("Retry-After")
            try:
                wait_seconds = float(retry_after) if retry_after else 0.0
            except (TypeError, ValueError):
                wait_seconds = 0.0
            if wait_seconds <= 0.0:
                wait_seconds = backoff_factor * attempt
            jitter = random.uniform(0, 0.25 * wait_seconds)
            total_wait = wait_seconds + jitter
            print(f"Received 429. Waiting {total_wait:.2f}s before retry {attempt}/{max_attempts - 1}...")
            time.sleep(total_wait)

    # Save cookies we received for future runs
    try:
        jar.save(ignore_discard=True, ignore_expires=True)
    except OSError:
        pass
    return jar, request_headers


def fetch_page(
    url: str,
    jar: http.cookiejar.CookieJar,
    headers: dict[str, str],
    *,
    timeout: float = 15.0,
) -> tuple[str, bytes, dict[str, str]]:
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    request_headers = headers.copy()

    # Ensure the Cookie header matches the jar contents for this URL.
    try:
        url_cookie_header = _cookie_header_from_jar_for_url(jar, url)
    except Exception:
        url_cookie_header = ""
    if url_cookie_header:
        request_headers["Cookie"] = url_cookie_header

    request = urllib.request.Request(url=url, headers=request_headers)
    with opener.open(request, timeout=timeout) as response:
        body = response.read()
        encoding = response.headers.get("Content-Encoding", "").lower()
        decoded = _decode_body(body, encoding)
        response_headers = {k: v for k, v in response.headers.items()}
        return decoded, body, response_headers


def _strip_html(text: str) -> str:
    if not text:
        return ""
    soup = BeautifulSoup(text, "html.parser")
    return soup.get_text(" ", strip=True)


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
        content.append(hero | {"sequence": image_counter})
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
            soup = BeautifulSoup(rendered, "html.parser")
            text = soup.get_text(" ", strip=True)
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
        else:
            continue
    return content


def extract_article_content(html: str, base_url: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    hero_entry: dict[str, Any] | None = None
    next_script = soup.find("script", id="__NEXT_DATA__")
    if next_script and next_script.string:
        try:
            data = json.loads(next_script.string)
            page_props = data.get("props", {}).get("pageProps", {})
            post_data = page_props.get("post", {})
            hide_featured = post_data.get("hideFeaturedImageOnArticlePage")
            if isinstance(hide_featured, dict):
                hide_featured = hide_featured.get("hidefeaturedimage")
            hero_node = (
                {} if hide_featured else post_data.get("featuredImage", {})
            )
            if isinstance(hero_node, dict):
                hero_node = hero_node.get("node") if "node" in hero_node else hero_node
            if isinstance(hero_node, dict):
                hero_entry = _hero_entry(hero_node, base_url)
            blocks = (
                data.get("props", {})
                .get("pageProps", {})
                .get("post", {})
                .get("editorBlocks", [])
            )
            if isinstance(blocks, list) and blocks:
                return _extract_from_editor_blocks(blocks, base_url, hero=hero_node)
        except (json.JSONDecodeError, TypeError):
            pass

    return _extract_from_dom(soup, base_url, hero=hero_entry)


def _extension_from_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    path = parsed.path
    _, ext = os.path.splitext(path)
    return ext if ext else ".bin"


def download_images(
    image_entries: Sequence[dict[str, Any]],
    *,
    jar: http.cookiejar.CookieJar,
    headers: dict[str, str],
    dest_dir: pathlib.Path,
    timeout: float = 15.0,
) -> list[dict[str, Any]]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    saved_by_url: dict[str, pathlib.Path] = {}
    downloaded: list[dict[str, Any]] = []
    unique_counter = 0
    for entry in image_entries:
        try:
            sequence = int(entry.get("sequence", 0))
        except (TypeError, ValueError):
            sequence = 0
        url = str(entry.get("url") or "").strip()
        if not url or sequence <= 0:
            downloaded.append({"sequence": sequence, "url": url, "path": None})
            continue
        if url in saved_by_url:
            downloaded.append({"sequence": sequence, "url": url, "path": saved_by_url[url]})
            continue

        request_headers = headers.copy()
        try:
            jar_cookie_header = _cookie_header_from_jar_for_url(jar, url)
        except Exception:
            jar_cookie_header = ""
        if jar_cookie_header:
            request_headers["Cookie"] = jar_cookie_header
        request = urllib.request.Request(url=url, headers=request_headers)
        unique_counter += 1
        filename = f"image_{unique_counter:03d}{_extension_from_url(url)}"
        dest_path = dest_dir / filename
        with opener.open(request, timeout=timeout) as response:
            data = response.read()
        dest_path.write_bytes(data)
        saved_by_url[url] = dest_path
        downloaded.append({"sequence": sequence, "url": url, "path": dest_path})
    return downloaded


def save_article_to_disk(
    content: list[dict[str, Any]],
    downloaded_images: Sequence[dict[str, Any]],
    dest_dir: pathlib.Path,
) -> pathlib.Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    output_path = dest_dir / "core_paragraphs.txt"
    lines: list[str] = []

    for entry in content:
        kind = entry.get("kind")
        if kind == "heading":
            lines.append(f"## {entry['text']}")
            lines.append("")
            continue

        if kind == "paragraph":
            text = entry.get("text") or "(no text)"
            lines.append(text)
            lines.append("")
            continue

        if kind == "image":
            sequence = entry.get("sequence")
            try:
                sequence_int = int(sequence)
            except (TypeError, ValueError):
                sequence_int = 0
            marker = f"{{{{[Image {sequence_int}]}}}}" if sequence_int else "{{[Image]}}"
            lines.append(marker)
            lines.append("")
            continue

        text = entry.get("text")
        if text:
            lines.append(text)
            lines.append("")

    output_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return output_path


def main() -> None:
    base_url = "https://www.realtor.com/news/trends/fed-chair-jerome-powell-speech-today/"
    # Use query parameters if the site requires them; change as needed.
    query = urllib.parse.urlencode({})
    url = f"{base_url}?{query}" if query else base_url
    print("Getting Cookie")
    jar, base_headers = fetch_cookies(url, min_delay=0.5, max_delay=1.5)
    if not jar:
        print("No cookies were returned.")
        return

    print("Cookies get successfully")

    # Build a fresh Cookie header for this URL from the jar and update config
    try:
        cookie_header = _cookie_header_from_jar_for_url(jar, url)
    except Exception:
        cookie_header = ""
    if cookie_header:
        if update_cookie_header_in_config(base_headers, cookie_header):
            print("Updated stored Cookie header in default_headers.json")
        else:
            print("Cookie header unchanged in config (no update needed)")

    print("Fetching page with updated cookies…")
    html, _, _ = fetch_page(url, jar, base_headers)
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    html_path = ASSET_DIR / "page.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"Saved raw HTML to {html_path}")
    content = extract_article_content(html, url)
    if not content:
        print("No .core-paragraph sections found.")
        return

    paragraph_count = sum(1 for entry in content if entry.get("kind") == "paragraph")
    image_entries = [entry for entry in content if entry.get("kind") == "image"]

    print(f"Found {paragraph_count} paragraphs and {len(image_entries)} images.")
    downloaded_images = download_images(
        image_entries,
        jar=jar,
        headers=base_headers,
        dest_dir=ASSET_DIR,
    )
    text_path = save_article_to_disk(content, downloaded_images, ASSET_DIR)
    print(f"Saved paragraph summary to {text_path}")
    saved_count = sum(1 for item in downloaded_images if item.get("path"))
    if saved_count:
        print(f"Saved {saved_count} images to {ASSET_DIR.resolve()}")


if __name__ == "__main__":
    main()
