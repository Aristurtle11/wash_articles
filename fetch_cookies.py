import gzip
import http.cookiejar
import json
import random
import time
import urllib.parse
import urllib.request
import zlib


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
    "Referer": "https://www.myself.com/",
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
}


def _decode_body(body: bytes, encoding: str) -> str:
    if not encoding:
        return body.decode(errors="replace")
    if encoding == "gzip":
        return gzip.decompress(body).decode(errors="replace")
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
        return brotli.decompress(body).decode(errors="replace")
    return f"<unsupported encoding {encoding}>"


def fetch_cookies(
    url: str,
    headers: dict[str, str] | None = None,
    *,
    min_delay: float = 0.0,
    max_delay: float = 0.0,
) -> http.cookiejar.CookieJar:
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    request_headers = DEFAULT_HEADERS.copy()
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url=url, headers=request_headers)
    if max_delay > 0:
        delay = random.uniform(min_delay, max_delay)
        if delay > 0:
            time.sleep(delay)
    with opener.open(request, timeout=10) as response:
        body = response.read()
        encoding = response.headers.get("Content-Encoding", "").lower()
        snippet = _decode_body(body[:4096], encoding)
        print("Response snippet:", json.dumps(snippet[:200]))
    return jar


def main() -> None:
    base_url = "https://www.myself.com/"
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


if __name__ == "__main__":
    main()
