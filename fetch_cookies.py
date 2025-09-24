import gzip
import http.cookiejar
import io
import json
import os
import random
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib


COOKIE_JAR_FILE = "cookies.txt"
HEADERS_FILE = "default_headers.json"
HEADERS_TEMPLATE_FILE = "default_headers.template.json"


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


def main() -> None:
    base_url = "https://www.realtor.com/"
    # Use query parameters if the site requires them; change as needed.
    query = urllib.parse.urlencode({})
    url = f"{base_url}?{query}" if query else base_url
    jar, base_headers = fetch_cookies(url, min_delay=0.5, max_delay=1.5)
    if not jar:
        print("No cookies were returned.")
        return

    print("Cookies from", url)
    for cookie in jar:
        print(f"{cookie.name}={cookie.value}")

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


if __name__ == "__main__":
    main()
