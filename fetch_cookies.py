import gzip
import http.cookiejar
import io
import json
import random
import time
import urllib.error
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
    "Cookie": "split_tcv=184; __ssn=08300b29-c5eb-4555-b9c6-0a0d1c473b2a; __ssnstarttime=1758678561; KP_UIDz-ssn=02PSQ5LS48xKaXydfxS07lXecCNoxyhjpB2nacA4Bq6OE5pFAy4IR3EYrwkWmkrAVyThLlXr8Kkmrtm7zZRieQoLvudq411auJYtNotUgAnix11SLr6r3O9KgYPtDzNVcXhs0fdSvvjRD3Q4HbGh48Ihcbx1bV8LcHlggaympD3Swt; KP_UIDz=02PSQ5LS48xKaXydfxS07lXecCNoxyhjpB2nacA4Bq6OE5pFAy4IR3EYrwkWmkrAVyThLlXr8Kkmrtm7zZRieQoLvudq411auJYtNotUgAnix11SLr6r3O9KgYPtDzNVcXhs0fdSvvjRD3Q4HbGh48Ihcbx1bV8LcHlggaympD3Swt; __vst=3fff1967-043d-4f49-bfae-cad8ff2071bf; __bot=false; __split=76; __rdc_id=rdc-id-cfa08541-2372-47da-b03a-e1c425d9680e; split=n; AWSALBTG=6drg5T7FtVTT3nFQNOKYhE3k6iGPosQpQP1CHrvboyaVIWAc5sM7T/YY+FGvi03MOWMr5AklFeZTsaOa0g0PxEp6Ezabf7huHhHi2XBsKSHf2TF1SAyF7tbk8XZ3KBHtLZNdOISlg1VzLco8z2n+mrYt+bwanP85PRx1RvlE6yy0; AWSALBTGCORS=6drg5T7FtVTT3nFQNOKYhE3k6iGPosQpQP1CHrvboyaVIWAc5sM7T/YY+FGvi03MOWMr5AklFeZTsaOa0g0PxEp6Ezabf7huHhHi2XBsKSHf2TF1SAyF7tbk8XZ3KBHtLZNdOISlg1VzLco8z2n+mrYt+bwanP85PRx1RvlE6yy0; AWSALB=pjHmr4qjzX6IqOH3Ot15jHF2s/hCJXaBBU3A33axo4Q//CEHPz15IG8k87xAF+OJ4+3DwbJRYwkdq2MGGz2Of9o2eHcgFdyyj5KrJLWAGeGQoZBsfBoPahd3sw6m; AWSALBCORS=pjHmr4qjzX6IqOH3Ot15jHF2s/hCJXaBBU3A33axo4Q//CEHPz15IG8k87xAF+OJ4+3DwbJRYwkdq2MGGz2Of9o2eHcgFdyyj5KrJLWAGeGQoZBsfBoPahd3sw6m"
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
                decoded = _decode_body(body, encoding)
                print("Response snippet:", json.dumps(decoded[:200]))
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


if __name__ == "__main__":
    main()
