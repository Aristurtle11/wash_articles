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
from typing import Iterable, Any

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


def extract_core_paragraphs(html: str, base_url: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    paragraphs: list[dict[str, Any]] = []
    for index, node in enumerate(soup.select(".core-paragraph"), start=1):
        text = node.get_text(strip=True)
        images: list[str] = []
        for img in node.find_all("img"):
            src = (img.get("src") or img.get("data-src") or "").strip()
            if not src:
                continue
            absolute = urllib.parse.urljoin(base_url, src)
            if absolute not in images:
                images.append(absolute)
        if text or images:
            paragraphs.append({"index": index, "text": text, "images": images})
    return paragraphs


def _extension_from_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    path = parsed.path
    _, ext = os.path.splitext(path)
    return ext if ext else ".bin"


def download_images(
    image_urls: Iterable[str],
    *,
    jar: http.cookiejar.CookieJar,
    headers: dict[str, str],
    dest_dir: pathlib.Path,
    timeout: float = 15.0,
) -> dict[str, pathlib.Path]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    saved: dict[str, pathlib.Path] = {}
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    for url in image_urls:
        if url in saved:
            continue
        request_headers = headers.copy()
        try:
            jar_cookie_header = _cookie_header_from_jar_for_url(jar, url)
        except Exception:
            jar_cookie_header = ""
        if jar_cookie_header:
            request_headers["Cookie"] = jar_cookie_header
        request = urllib.request.Request(url=url, headers=request_headers)
        filename = f"image_{len(saved) + 1:03d}{_extension_from_url(url)}"
        dest_path = dest_dir / filename
        with opener.open(request, timeout=timeout) as response:
            data = response.read()
        dest_path.write_bytes(data)
        saved[url] = dest_path
    return saved


def save_paragraphs_to_disk(
    paragraphs: list[dict[str, Any]],
    image_map: dict[str, pathlib.Path],
    dest_dir: pathlib.Path,
) -> pathlib.Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    output_path = dest_dir / "core_paragraphs.txt"
    lines: list[str] = []
    for paragraph in paragraphs:
        text = paragraph["text"] or "(no text)"
        lines.append(text)
        images = paragraph["images"]
        if images:
            lines.append("Images:")
            for img in images:
                local_path = image_map.get(img)
                lines.append(f"  - {img}")
                if local_path:
                    lines.append(f"    saved_as: {local_path.name}")
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
    paragraphs = extract_core_paragraphs(html, url)
    if not paragraphs:
        print("No .core-paragraph sections found.")
        return

    all_image_urls: list[str] = []
    for paragraph in paragraphs:
        for img in paragraph["images"]:
            if img not in all_image_urls:
                all_image_urls.append(img)

    print(f"Found {len(paragraphs)} paragraphs and {len(all_image_urls)} unique images.")
    image_map = download_images(
        all_image_urls,
        jar=jar,
        headers=base_headers,
        dest_dir=ASSET_DIR,
    )
    text_path = save_paragraphs_to_disk(paragraphs, image_map, ASSET_DIR)
    print(f"Saved paragraph summary to {text_path}")
    if image_map:
        print(f"Saved {len(image_map)} images to {ASSET_DIR.resolve()}")


if __name__ == "__main__":
    main()
