import gzip
import http.cookiejar
import io
import json
import os
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib


COOKIE_JAR_FILE = "cookies.txt"


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"\
        "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Referer": "https://www.realtor.com/",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Sec-CH-UA": '"Not;A=Brand";v="99", "Google Chrome";v="139", "Chromium";v="139"',
    "Sec-CH-UA-Mobile": "?0",
    "Sec-CH-UA-Platform": '"Windows"',
    "DNT": "1",
    "Priority": "u=0, i",
    "Cookie": "KP_UIDz=03d8PZjH7PAqHcJvX8aUEiMKlUHeKgF1xpATLJUH1PRH5M8AH9AK1nRELidVnvypeYwoOZMy7hwuoBBk8Z1mOyZXhSiVOVGRSmDZJRu5kYuHIangs7oSvtSS46Lc6oXs5jPpOvDUpccc2DOrT97VGJFpgECDfsenaJnCh92Y7nDkZp; KP_UIDz-ssn=03d8PZjH7PAqHcJvX8aUEiMKlUHeKgF1xpATLJUH1PRH5M8AH9AK1nRELidVnvypeYwoOZMy7hwuoBBk8Z1mOyZXhSiVOVGRSmDZJRu5kYuHIangs7oSvtSS46Lc6oXs5jPpOvDUpccc2DOrT97VGJFpgECDfsenaJnCh92Y7nDkZp; __bot=false; __ssn=612f7111-6674-42ce-aa98-60b2acf37a6b; __ssnstarttime=1758681753; __vst=3fff1967-043d-4f49-bfae-cad8ff2071bf; split=v; split_tcv=184"
}


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


def _escape_cookie_value_for_source(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _cookie_header_from_jar_for_url(jar: http.cookiejar.CookieJar, url: str) -> str:
    # Let CookieJar compute the correct Cookie header for the URL.
    req = urllib.request.Request(url)
    jar.add_cookie_header(req)
    return req.get_header("Cookie", "")


def _update_cookie_header_in_source(new_cookie_header: str, *, source_path: str | None = None) -> bool:
    """Update the DEFAULT_HEADERS["Cookie"] literal in this source file.

    Returns True if an update was applied.
    """
    if not new_cookie_header:
        return False
    path = source_path or __file__
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return False

    # Replace the first occurrence of the Cookie header value inside DEFAULT_HEADERS.
    pattern = r'(\"Cookie\"\s*:\s*)\"[^\"]*\"'
    replacement = r"\\1\"" + _escape_cookie_value_for_source(new_cookie_header) + r"\""
    new_content, n = re.subn(pattern, replacement, content, count=1)
    if n == 0:
        # Fallback with a simpler pattern (no escaped quotes in source)
        pattern2 = r'("Cookie"\s*:\s*)"[^"]*"'
        replacement2 = r'\1"' + _escape_cookie_value_for_source(new_cookie_header) + r'"'
        new_content, n = re.subn(pattern2, replacement2, content, count=1)
    if n == 0 or new_content == content:
        return False
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
        return True
    except OSError:
        return False


def update_cookie_header_in_source_safe(new_cookie_header: str, *, source_path: str | None = None) -> bool:
    """Robustly update DEFAULT_HEADERS["Cookie"] in this file.

    - Uses a lambda replacement to avoid backreference escape issues.
    - If the Cookie line is missing/corrupted, inserts a fixed line after the
      "Priority" header within DEFAULT_HEADERS.
    """
    if not new_cookie_header:
        return False
    path = source_path or __file__
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return False

    escaped = _escape_cookie_value_for_source(new_cookie_header)
    # Try replacing an existing Cookie line.
    pattern = r'("Cookie"\s*:\s*)"[^"]*"'
    new_content, n = re.subn(pattern, lambda m: m.group(1) + '"' + escaped + '"', content, count=1)
    if n == 0:
        # Insert/fix the Cookie line right after the Priority line.
        mp = re.search(r'(?m)^(\s*)"Priority"\s*:\s*.*$', content)
        if not mp:
            return False
        indent = mp.group(1)
        eol = content.find("\n", mp.end())
        if eol == -1:
            return False
        next_start = eol + 1
        next_eol = content.find("\n", next_start)
        if next_eol == -1:
            next_eol = len(content)
        cookie_line = f'{indent}"Cookie": "{escaped}"\n'
        new_content = content[:next_start] + cookie_line + content[next_eol:]
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
        return True
    except OSError:
        return False

def fetch_cookies(
    url: str,
    headers: dict[str, str] | None = None,
    *,
    min_delay: float = 0.0,
    max_delay: float = 0.0,
) -> http.cookiejar.CookieJar:
    # Persist cookies across runs
    jar = http.cookiejar.MozillaCookieJar(COOKIE_JAR_FILE)
    if os.path.exists(COOKIE_JAR_FILE):
        try:
            jar.load(ignore_discard=True, ignore_expires=True)
        except (OSError, http.cookiejar.LoadError):
            pass
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    request_headers = DEFAULT_HEADERS.copy()
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
    if delay > 0:
        time.sleep(delay)
    with opener.open(request, timeout=10) as response:
        body = response.read()
        encoding = response.headers.get("Content-Encoding", "").lower()
        decoded = _decode_body(body, encoding)
        print("Response snippet:", json.dumps(decoded[:200]))

    # Save cookies we received for future runs
    try:
        jar.save(ignore_discard=True, ignore_expires=True)
    except OSError:
        pass
    return jar


def main() -> None:
    base_url = "https://www.realtor.com/"
    # Use query parameters if the site requires them; change as needed.
    query = urllib.parse.urlencode({})
    url = f"{base_url}?{query}" if query else base_url
    cookies = fetch_cookies(url, min_delay=0.5, max_delay=1.5)
    if not cookies:
        print("No cookies were returned.")
        return

    print("Cookies from", url)
    for cookie in cookies:
        print(f"{cookie.name}={cookie.value}")

    # Build a fresh Cookie header for this URL from the jar and update source
    try:
        cookie_header = _cookie_header_from_jar_for_url(cookies, url)
    except Exception:
        cookie_header = ""
    if cookie_header:
        if update_cookie_header_in_source_safe(cookie_header):
            print("Updated hardcoded Cookie header in fetch_cookies.py")
        else:
            print("Cookie header unchanged in source (no update needed)")


if __name__ == "__main__":
    main()
