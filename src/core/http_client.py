"""HTTP client with cookie persistence and retry support."""

from __future__ import annotations

import gzip
import http.cookiejar
import io
import json
import logging
import random
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from ..settings import HttpSettings, PathSettings, load_default_headers
from .rate_limiter import RateLimiter


_LOGGER = logging.getLogger(__name__)
_EXCLUDED_HEADER_KEYS = {"cookie", "cookie2", "host", "content-length"}
_BROWSER_HEADER_SKIP = {
    "cookie",
    "user-agent",
    "accept-encoding",
    "content-length",
    "connection",
    "host",
}
_BROWSER_HEADER_ALLOW = {
    "referer",
    "sec-ch-ua",
    "sec-ch-ua-mobile",
    "sec-ch-ua-platform",
    "sec-fetch-dest",
    "sec-fetch-mode",
    "sec-fetch-site",
    "sec-fetch-user",
    "upgrade-insecure-requests",
    "pragma",
    "cache-control",
}
_CANONICAL_HEADER_NAMES = {
    "user-agent": "User-Agent",
    "accept": "Accept",
    "accept-language": "Accept-Language",
    "accept-encoding": "Accept-Encoding",
    "cache-control": "Cache-Control",
    "pragma": "Pragma",
    "dnt": "DNT",
    "priority": "Priority",
    "referer": "Referer",
    "sec-ch-ua": "Sec-CH-UA",
    "sec-ch-ua-mobile": "Sec-CH-UA-Mobile",
    "sec-ch-ua-platform": "Sec-CH-UA-Platform",
    "sec-fetch-dest": "Sec-Fetch-Dest",
    "sec-fetch-mode": "Sec-Fetch-Mode",
    "sec-fetch-site": "Sec-Fetch-Site",
    "sec-fetch-user": "Sec-Fetch-User",
    "upgrade-insecure-requests": "Upgrade-Insecure-Requests",
    "cookie": "Cookie",
    "cookie2": "Cookie2",
    "host": "Host",
    "connection": "Connection",
}


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
        paths: PathSettings,
        transport: str | None = None,
    ) -> None:
        self._http_settings = http_settings
        self._cookie_path = paths.cookie_jar
        self._header_path = paths.header_jar
        self._use_captured_headers = bool(getattr(http_settings, "use_captured_headers", False))
        self._default_headers: dict[str, str] = self._load_header_context()
        self._transport = (transport or getattr(http_settings, "transport", "auto") or "auto").lower()
        self._playwright_channel = getattr(http_settings, "playwright_channel", None)
        headless = getattr(http_settings, "playwright_headless", True)
        self._playwright_headless = bool(headless)

        self._cookie_path.parent.mkdir(parents=True, exist_ok=True)
        self._header_path.parent.mkdir(parents=True, exist_ok=True)
        self._persist_headers()

        self._cookie_jar = http.cookiejar.MozillaCookieJar(str(self._cookie_path))
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
        if self._transport == "browser":
            return self._fetch_with_browser(request)
        try:
            return self._fetch_with_urllib(request)
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and self._transport == "auto":
                _LOGGER.warning("HTTP 429 detected; retrying with browser transport")
                return self._fetch_with_browser(request)
            raise

    def _fetch_with_urllib(self, request: HttpRequest) -> HttpResponse:
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

    def _fetch_with_browser(self, request: HttpRequest) -> HttpResponse:
        try:
            from playwright.sync_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeout, sync_playwright
        except ModuleNotFoundError as exc:  # pragma: no cover - Playwright optional in tests
            raise RuntimeError("Playwright is required for browser transport") from exc

        headers = self._merge_headers(request.url, request.headers)
        timeout = request.timeout if request.timeout is not None else self._http_settings.timeout
        start_time = time.monotonic()

        with sync_playwright() as p:
            headless = getattr(self, "_playwright_headless", True)
            launch_kwargs = {
                "headless": headless,
                "chromium_sandbox": False,
                "args": [
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                ],
            }
            channel = getattr(self, "_playwright_channel", None)
            if channel:
                launch_kwargs["channel"] = channel
            browser = p.chromium.launch(**launch_kwargs)
            context_kwargs: dict[str, object] = {
                "viewport": {"width": 1280, "height": 720},
                "screen": {"width": 1280, "height": 720},
                "device_scale_factor": 1,
                "is_mobile": False,
                "has_touch": False,
            }
            user_agent = headers.get("User-Agent")
            if user_agent:
                context_kwargs["user_agent"] = user_agent
            locale = self._locale_from_headers(headers)
            if locale:
                context_kwargs["locale"] = locale
            context = browser.new_context(**context_kwargs)
            self._apply_stealth(context)
            extra_headers = self._browser_headers(headers)
            if extra_headers:
                context.set_extra_http_headers(extra_headers)
            self._sync_cookies_to_browser(context, request.url)
            page = context.new_page()
            timeout_ms = max(int(timeout * 1000), 45000)
            try:
                response = page.goto(request.url, wait_until="networkidle", timeout=timeout_ms)
            except PlaywrightTimeout:
                _LOGGER.debug("Initial goto networkidle timed out; retrying with domcontentloaded")
                response = page.goto(
                    request.url, wait_until="domcontentloaded", timeout=timeout_ms
                )
                try:
                    page.wait_for_load_state("networkidle", timeout=timeout_ms // 2)
                except PlaywrightTimeout:
                    _LOGGER.debug("networkidle wait still timed out after fallback")
            try:
                page.wait_for_function(
                    "() => !document.body.innerText.includes('Your request could not be processed')",
                    timeout=int(timeout * 1000 / 2),
                )
            except PlaywrightTimeout:
                _LOGGER.debug("Initial challenge wait timed out; continuing with fallback")
            try:
                body = page.content()
            except PlaywrightError as exc:
                _LOGGER.warning("Failed to collect page content (initial load): %s", exc)
                body = ""
            response_headers = response.all_headers() if response else {}
            status = response.status if response else 200

            for _ in range(3):
                if not self._looks_like_challenge(body, status):
                    break
                page.wait_for_timeout(3000)
                try:
                    response = page.reload(wait_until="networkidle", timeout=int(timeout * 1000))
                except PlaywrightTimeout:
                    _LOGGER.debug("Page reload timed out; stopping challenge retries")
                    break
                try:
                    page.wait_for_function(
                        "() => !document.body.innerText.includes('Your request could not be processed')",
                        timeout=int(timeout * 1000 / 2),
                    )
                except PlaywrightTimeout:
                    _LOGGER.debug("Challenge wait timed out during retry")
                try:
                    body = page.content()
                except PlaywrightError as exc:
                    _LOGGER.warning("Failed to collect page content after reload: %s", exc)
                    body = ""
                if response:
                    response_headers = response.all_headers()
                    status = response.status

            elapsed = time.monotonic() - start_time
            final_url = page.url
            self._sync_cookies_from_browser(context.cookies())
            context.close()
            browser.close()

        self._update_cookie_header(final_url)

        return HttpResponse(
            url=final_url,
            status=status,
            headers=response_headers,
            body=body.encode("utf-8"),
            text=body,
            elapsed=elapsed,
        )

    def _merge_headers(self, url: str, request_headers: Mapping[str, str] | None) -> dict[str, str]:
        headers = dict(self._default_headers)
        if request_headers:
            headers.update(self._canonicalize_headers(request_headers))
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
        self._persist_headers()

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

    def _load_header_context(self) -> dict[str, str]:
        fallback_raw = load_default_headers()
        fallback = self._canonicalize_headers(fallback_raw)
        headers = dict(fallback)

        if self._use_captured_headers:
            stored = self._read_headers_file(self._header_path)
            if stored:
                captured = self._canonicalize_headers(stored)
                cookie_header = captured.pop("Cookie", None)
                if cookie_header:
                    self._apply_cookie_header(cookie_header)
                for key, value in captured.items():
                    if key == "Sec-CH-UA" and "Headless" in value:
                        continue
                    headers[key] = value

        if "Accept-Encoding" in headers:
            headers["Accept-Encoding"] = self._strip_unsupported_encodings(headers["Accept-Encoding"])

        return headers

    def _apply_cookie_header(self, header_value: str) -> None:
        try:
            from http.cookies import SimpleCookie
        except ImportError:  # pragma: no cover - fallback for minimal envs
            _LOGGER.warning("无法导入 SimpleCookie，跳过 Cookie 合并")
            return

        cookie = SimpleCookie()
        try:
            cookie.load(header_value)
        except Exception as exc:
            _LOGGER.warning("解析 Cookie 头失败: %s", exc)
            return

        changed = False
        for morsel in cookie.values():
            name = morsel.key
            value = morsel.value
            domain = morsel["domain"] or "www.realtor.com"
            path = morsel["path"] or "/"
            secure = bool(morsel["secure"])
            expires = None
            if morsel["expires"]:
                try:
                    expires = int(float(morsel["expires"]))
                except ValueError:
                    expires = None

            new_cookie = http.cookiejar.Cookie(
                version=0,
                name=name,
                value=value,
                port=None,
                port_specified=False,
                domain=domain,
                domain_specified=True,
                domain_initial_dot=domain.startswith("."),
                path=path,
                path_specified=True,
                secure=secure,
                expires=expires,
                discard=False,
                comment=None,
                comment_url=None,
                rest={},
            )
            self._cookie_jar.set_cookie(new_cookie)
            changed = True

        if changed:
            try:
                self._cookie_jar.save(ignore_discard=True, ignore_expires=True)
            except Exception as exc:  # pragma: no cover - best effort
                _LOGGER.debug("保存合并后的 Cookie 失败: %s", exc)

    def _apply_stealth(self, context) -> None:
        script = """
        (() => {
          const define = (obj, key, value) => {
            try {
              Object.defineProperty(obj, key, { get: () => value });
            } catch (err) {
              try { obj[key] = value; } catch (_) { /* noop */ }
            }
          };

          define(navigator, 'webdriver', undefined);
          window.navigator.chrome = { runtime: {} };
          define(navigator, 'languages', ['en-US', 'en']);
          define(navigator, 'platform', 'Win32');
          define(navigator, 'maxTouchPoints', 0);
          define(navigator, 'hardwareConcurrency', 8);
          define(navigator, 'pdfViewerEnabled', true);
          define(navigator, 'plugins', [1, 2, 3, 4, 5]);

          if (!navigator.userAgentData) {
            const data = {
              brands: [
                { brand: 'Not.A/Brand', version: '8' },
                { brand: 'Chromium', version: '125' },
                { brand: 'Google Chrome', version: '125' }
              ],
              mobile: false,
              platform: 'Windows',
              getHighEntropyValues: () => Promise.resolve({
                architecture: 'x86',
                platformVersion: '15.0.0',
                model: '',
                uaFullVersion: '125.0.6422.60',
                bitness: '64',
                brands: [
                  { brand: 'Not.A/Brand', version: '8' },
                  { brand: 'Chromium', version: '125' },
                  { brand: 'Google Chrome', version: '125' }
                ],
                fullVersionList: [
                  { brand: 'Not.A/Brand', version: '8.0.0.0' },
                  { brand: 'Chromium', version: '125.0.6422.60' },
                  { brand: 'Google Chrome', version: '125.0.6422.60' }
                ]
              }),
            };
            define(navigator, 'userAgentData', data);
          }

          const originalQuery = navigator.permissions.query.bind(navigator.permissions);
          navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications'
              ? Promise.resolve({ state: Notification.permission })
              : originalQuery(parameters)
          );

          const getParameter = WebGLRenderingContext.prototype.getParameter;
          WebGLRenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) return 'Intel Inc.';
            if (parameter === 37446) return 'Intel(R) Iris(R) Graphics';
            return getParameter.call(this, parameter);
          };

          const getParameter2 = WebGL2RenderingContext && WebGL2RenderingContext.prototype.getParameter;
          if (getParameter2) {
            WebGL2RenderingContext.prototype.getParameter = function(parameter) {
              if (parameter === 37445) return 'Intel Inc.';
              if (parameter === 37446) return 'Intel(R) Iris(R) Graphics';
              return getParameter2.call(this, parameter);
            };
          }

          define(screen, 'availHeight', window.innerHeight);
          define(screen, 'availWidth', window.innerWidth);
          define(screen, 'colorDepth', 24);
          define(screen, 'pixelDepth', 24);
          define(window, 'outerWidth', window.innerWidth);
          define(window, 'outerHeight', window.innerHeight + 72);
        })();
        """
        context.add_init_script(script)

    def _read_headers_file(self, path: Path) -> dict[str, str] | None:
        try:
            with path.open("r", encoding="utf-8") as fp:
                data = json.load(fp)
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError) as exc:
            _LOGGER.warning("加载 header_jar 失败 (%s): %s", path, exc)
            return None
        return {str(k): str(v) for k, v in data.items()}

    def _persist_headers(self) -> None:
        try:
            with self._header_path.open("w", encoding="utf-8") as fp:
                json.dump(self._default_headers, fp, ensure_ascii=False, indent=2, sort_keys=True)
        except OSError as exc:
            _LOGGER.warning("写入 header_jar 失败 (%s): %s", self._header_path, exc)
    def _canonicalize_headers(self, raw: Mapping[str, str]) -> dict[str, str]:
        canonical: dict[str, str] = {}
        for key, value in raw.items():
            key_str = str(key).strip()
            if not key_str or key_str.startswith(":"):
                continue
            lower = key_str.lower()
            if lower in _EXCLUDED_HEADER_KEYS:
                continue
            canonical_key = _CANONICAL_HEADER_NAMES.get(lower, key_str)
            canonical[canonical_key] = str(value)
        return canonical

    def _strip_unsupported_encodings(self, value: str) -> str:
        encodings = [item.strip() for item in value.split(",") if item.strip()]
        supported = []
        for encoding in encodings:
            if encoding.lower() == "zstd":
                continue
            supported.append(encoding)
        return ", ".join(supported) if supported else value

    def _looks_like_challenge(self, body: str, status: int) -> bool:
        if status == 429:
            return True
        markers = [
            "Your request could not be processed",
            "kpsdk",
            "unblockrequest@realtor.com",
        ]
        body_lower = body.lower()
        return any(marker.lower() in body_lower for marker in markers)

    def _browser_headers(self, headers: Mapping[str, str]) -> dict[str, str]:
        filtered: dict[str, str] = {}
        for key, value in headers.items():
            key_lower = key.lower()
            if key_lower in _BROWSER_HEADER_SKIP:
                continue
            if key_lower not in _BROWSER_HEADER_ALLOW:
                continue
            filtered[key] = value
        return filtered

    def _locale_from_headers(self, headers: Mapping[str, str]) -> str | None:
        accept_language = headers.get("accept-language")
        if not accept_language:
            return None
        primary = accept_language.split(",", 1)[0].strip()
        return primary or None

    def _sync_cookies_to_browser(self, context, url: str) -> None:
        cookies: list[dict[str, object]] = []
        for cookie in self._cookie_jar:
            cookie_dict: dict[str, object] = {
                "name": cookie.name,
                "value": cookie.value,
                "domain": cookie.domain,
                "path": cookie.path,
                "secure": cookie.secure,
            }
            if cookie.expires is not None:
                cookie_dict["expires"] = cookie.expires
            rest = getattr(cookie, "_rest", {})
            if rest.get("HttpOnly") is not None:
                cookie_dict["httpOnly"] = True
            cookies.append(cookie_dict)
        if cookies:
            context.add_cookies(cookies)

    def _sync_cookies_from_browser(self, cookies: list[dict[str, object]]) -> None:
        changed = False
        for cookie in cookies:
            name = str(cookie.get("name"))
            value = str(cookie.get("value", ""))
            domain = str(cookie.get("domain", ""))
            path = str(cookie.get("path", "/"))
            expires_raw = cookie.get("expires")
            expires = int(expires_raw) if isinstance(expires_raw, (int, float)) and expires_raw > 0 else None
            secure = bool(cookie.get("secure", False))
            http_only = bool(cookie.get("httpOnly", False))
            new_cookie = http.cookiejar.Cookie(
                version=0,
                name=name,
                value=value,
                port=None,
                port_specified=False,
                domain=domain,
                domain_specified=bool(domain),
                domain_initial_dot=domain.startswith("."),
                path=path,
                path_specified=True,
                secure=secure,
                expires=expires,
                discard=False,
                comment=None,
                comment_url=None,
                rest={"HttpOnly": None} if http_only else {},
            )
            self._cookie_jar.set_cookie(new_cookie)
            changed = True
        if changed:
            self._cookie_jar.save(ignore_discard=True, ignore_expires=True)

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
