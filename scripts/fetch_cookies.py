"""
Utility script to refresh cookies for a given URL using Playwright to handle JS challenges.
"""

from __future__ import annotations

import argparse
import asyncio
import http.cookiejar
import json
import sys
from pathlib import Path
from typing import Sequence

from playwright.async_api import Request, async_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.settings import load_config
from src.utils.logging import configure_logging, get_logger

LOGGER = get_logger(__name__)

# A realistic User-Agent is crucial for avoiding detection. Match Playwright's bundled Chromium.
REALISTIC_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


async def fetch(url: str, *, config_path: str | None = None) -> None:
    """
    Fetches a URL using Playwright, waits for JS challenges to complete,
    and saves the resulting cookies to a file compatible with http.cookiejar.
    """
    config = load_config(config_path)
    cookie_file_path = config.paths.cookie_jar
    header_file_path = config.paths.header_jar

    LOGGER.info("Starting Playwright to fetch cookies from %s", url)
    LOGGER.info("Cookies will be saved to %s", cookie_file_path)

    captured_headers: dict[str, str] | None = None
    header_event = asyncio.Event()

    async def _capture_navigation_headers(request: Request) -> None:
        nonlocal captured_headers
        if captured_headers is not None:
            return
        if not request.is_navigation_request():
            return
        raw_headers = await request.all_headers()
        filtered: dict[str, str] = {}
        for raw_key, raw_value in raw_headers.items():
            key_str = str(raw_key)
            key_lower = key_str.lower()
            if key_str.startswith(":") or key_lower in {"cookie", "cookie2", "host", "content-length"}:
                continue
            filtered[key_str] = str(raw_value)
        captured_headers = filtered
        header_event.set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            chromium_sandbox=False,
            args=["--disable-dev-shm-usage"],
        )
        context = await browser.new_context(user_agent=REALISTIC_USER_AGENT)
        page = await context.new_page()
        page.on("request", lambda req: asyncio.create_task(_capture_navigation_headers(req)))

        try:
            LOGGER.info("Navigating to the page...")
            # Using 'networkidle' helps ensure that most dynamic content and JS challenges have finished.
            await page.goto(url, wait_until="networkidle", timeout=60000)
            LOGGER.info("Page loaded successfully. Extracting cookies.")

            if captured_headers is None:
                try:
                    await asyncio.wait_for(header_event.wait(), timeout=5)
                except asyncio.TimeoutError:
                    LOGGER.warning("等待导航请求头超时，可能未捕获完整指纹")

            # Extract cookies from the browser context
            cookies = await context.cookies()

            # Save cookies in the Netscape format, which is used by http.cookiejar
            cookie_jar = http.cookiejar.MozillaCookieJar()
            for cookie in cookies:
                c = http.cookiejar.Cookie(
                    version=0,
                    name=cookie["name"],
                    value=cookie["value"],
                    port=None,
                    port_specified=False,
                    domain=cookie["domain"],
                    domain_specified=True,
                    domain_initial_dot=cookie["domain"].startswith("."),
                    path=cookie["path"],
                    path_specified=True,
                    secure=cookie["secure"],
                    expires=cookie["expires"] if cookie["expires"] != -1 else None,
                    discard=False,
                    comment=None,
                    comment_url=None,
                    rest={},
                )
                cookie_jar.set_cookie(c)

            cookie_file_path.parent.mkdir(parents=True, exist_ok=True)
            cookie_jar.save(cookie_file_path, ignore_discard=True, ignore_expires=True)

            LOGGER.info("Successfully saved %d cookies to %s", len(cookie_jar), cookie_file_path)

            if captured_headers:
                header_file_path.parent.mkdir(parents=True, exist_ok=True)
                with header_file_path.open("w", encoding="utf-8") as fp:
                    json.dump(captured_headers, fp, ensure_ascii=False, indent=2, sort_keys=True)
                LOGGER.info("Captured %d headers to %s", len(captured_headers), header_file_path)
            else:
                LOGGER.warning("未捕获到导航请求头，header_jar 未更新")

        except Exception as e:
            LOGGER.error("An error occurred during Playwright operation: %s", e)
            LOGGER.info("Taking a screenshot for debugging to playwright-error.png")
            await page.screenshot(path="playwright-error.png")
        finally:
            await browser.close()
            LOGGER.info("Playwright browser closed.")


def main(argv: Sequence[str] | None = None) -> None:
    configure_logging()
    parser = argparse.ArgumentParser(
        description="Fetch cookies using a real browser to solve JS challenges."
    )
    parser.add_argument("url", help="URL to request")
    parser.add_argument("--config", help="Alternative config path")
    args = parser.parse_args(argv)
    asyncio.run(fetch(args.url, config_path=args.config))


if __name__ == "__main__":
    main()
