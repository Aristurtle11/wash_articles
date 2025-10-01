"""HTTP client with cookie persistence and retry support."""

from __future__ import annotations

import gzip
import http.cookiejar
import io
import random
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, MutableMapping

from ..settings import HttpSettings, save_default_headers
from .rate_limiter import RateLimiter


@dataclass(slots=True)
class HttpRequest:
    url: str
    method: str = "GET"
    headers: Mapping[str, str] | None = None
    data: bytes | None = None
    min_delay: float | None = None
    max_delay: float | None = None
    max_attempts: int | None = None
    backoff_factor: float | None = None
    timeout: float | None = None


@dataclass(slots=True)
class HttpResponse:
    url: str
    status: int
    headers: Mapping[str, str]
    body: bytes
    text: str
    elapsed: float


class HttpClient:
    """Stateful HTTP client backed by ``urllib`` and ``MozillaCookieJar``."""

    def __init__(
        self,
        *,
        http_settings: HttpSettings,
        cookie_path: Path,
        default_headers: MutableMapping[str, str] | None = None,
        header_saver: Callable[[dict[str, str]], None] | None = save_default_headers,
    ) -> None:
        self._http_settings = http_settings
        self._cookie_path = cookie_path
        self._header_saver = header_saver
        self._default_headers: dict[str, str] = dict(default_headers or {})

        cookie_path.parent.mkdir(parents=True, exist_ok=True)
        self._cookie_jar = http.cookiejar.MozillaCookieJar(str(cookie_path))
        self._load_cookie_jar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._cookie_jar)
        )

    @property
    def cookie_path(self) -> Path:
        return self._cookie_path

    @property
    def default_headers(self) -> dict[str, str]:
        return dict(self._default_headers)

    def fetch(self, request: HttpRequest) -> HttpResponse:
        headers = self._merge_headers(request.url, request.headers)
        rate_limiter = RateLimiter(
            min_delay=request.min_delay
            if request.min_delay is not None
            else self._http_settings.min_delay,
            max_delay=request.max_delay
            if request.max_delay is not None
            else self._http_settings.max_delay,
        )

        if rate_limiter.min_delay > 0 or rate_limiter.max_delay > 0:
            rate_limiter.sleep()

        req = urllib.request.Request(
            url=request.url,
            headers=headers,
            data=request.data,
            method=request.method.upper(),
        )
        timeout = request.timeout if request.timeout is not None else self._http_settings.timeout
        max_attempts = (
            request.max_attempts
            if request.max_attempts is not None
            else self._http_settings.max_attempts
        )
        backoff_factor = (
            request.backoff_factor
            if request.backoff_factor is not None
            else self._http_settings.backoff_factor
        )

        attempt = 0
        start_time = time.monotonic()
        while True:
            try:
                with self._opener.open(req, timeout=timeout) as resp:
                    body = resp.read()
                    encoding = resp.headers.get("Content-Encoding", "").lower()
                    text = self._decode_body(body, encoding)
                    elapsed = time.monotonic() - start_time
                    self._cookie_jar.save(ignore_discard=True, ignore_expires=True)
                    self._update_cookie_header(request.url)
                    return HttpResponse(
                        url=resp.geturl(),
                        status=getattr(resp, "status", 200),
                        headers=dict(resp.headers.items()),
                        body=body,
                        text=text,
                        elapsed=elapsed,
                    )
            except urllib.error.HTTPError as exc:
                attempt += 1
                if exc.code != 429 or attempt >= max_attempts:
                    raise
                wait_seconds = self._compute_retry_wait(exc, attempt, backoff_factor)
                time.sleep(wait_seconds)

    def _merge_headers(self, url: str, request_headers: Mapping[str, str] | None) -> dict[str, str]:
        headers = dict(self._default_headers)
        if request_headers:
            headers.update({str(k): str(v) for k, v in request_headers.items()})
        cookie_header = self._cookie_header_for_url(url, headers.get("Cookie", ""))
        if cookie_header:
            headers["Cookie"] = cookie_header
        return headers

    def _cookie_header_for_url(
        self,
        url: str,
        existing_cookie: str,
    ) -> str:
        url_candidates = [url]
        try:
            parsed = urllib.parse.urlparse(url)
        except Exception:
            parsed = urllib.parse.urlparse("")
        if not parsed.scheme and parsed.netloc:
            url_candidates.append(f"https://{parsed.netloc}")
        for candidate_url in url_candidates:
            try:
                req = urllib.request.Request(candidate_url)
                self._cookie_jar.add_cookie_header(req)
                candidate = req.get_header("Cookie", "")
                if candidate:
                    return candidate
            except Exception:
                continue
        return existing_cookie

    def _update_cookie_header(self, url: str) -> None:
        try:
            req = urllib.request.Request(url)
            self._cookie_jar.add_cookie_header(req)
            new_cookie = req.get_header("Cookie", "")
        except Exception:
            return
        if not new_cookie:
            return
        current_cookie = self._default_headers.get("Cookie")
        if current_cookie == new_cookie:
            return
        self._default_headers["Cookie"] = new_cookie
        if self._header_saver:
            self._header_saver(dict(self._default_headers))

    def _load_cookie_jar(self) -> None:
        try:
            self._cookie_jar.load(ignore_discard=True, ignore_expires=True)
        except (FileNotFoundError, http.cookiejar.LoadError, OSError):
            self._cookie_jar.clear()

    def _decode_body(self, body: bytes, encoding: str) -> str:
        if not body:
            return ""
        encoding = encoding.lower().strip()
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
            except Exception as exc:  # pragma: no cover - type narrowed at runtime
                return f"<brotli decode failed: {exc}>"
        return f"<unsupported encoding {encoding}>"

    def _compute_retry_wait(
        self, exc: urllib.error.HTTPError, attempt: int, backoff_factor: float
    ) -> float:
        retry_after = exc.headers.get("Retry-After")
        wait_seconds = 0.0
        if retry_after:
            try:
                wait_seconds = float(retry_after)
            except (TypeError, ValueError):
                wait_seconds = 0.0
        if wait_seconds <= 0:
            wait_seconds = backoff_factor * attempt
        jitter = random.uniform(0, 0.25 * wait_seconds)
        return wait_seconds + jitter

    def as_dict(self) -> dict[str, str]:
        return dict(self._default_headers)
