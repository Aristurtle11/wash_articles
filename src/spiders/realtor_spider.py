from __future__ import annotations

from typing import Any, Iterable, Iterator
import urllib.parse
import logging

from bs4 import BeautifulSoup

from ..core.base_spider import BaseSpider
from ..core.http_client import HttpRequest, HttpResponse
from ..settings import project_path
from ..utils.realtor_extract import extract_article_content, render_content_to_text


LOGGER = logging.getLogger(__name__)


class RealtorSpider(BaseSpider):
    name = "realtor"

    def start_requests(self) -> Iterable[HttpRequest]:
        yield HttpRequest(url=self.config["start_url"])

    def parse(self, response: HttpResponse) -> Iterator[Any]:
        LOGGER.info("Parsing response from %s (status=%s, body=%d bytes)", response.url, response.status, len(response.body))
        raw_dir = project_path("data", "raw", self.name)
        raw_dir.mkdir(parents=True, exist_ok=True)

        slug = urllib.parse.urlparse(response.url).path.strip("/") or "index"
        safe_slug = slug.replace("/", "_")
        html_path = raw_dir / f"{safe_slug}.html"
        html_path.write_text(response.text, encoding="utf-8")
        LOGGER.info("Saved HTML to %s", html_path)

        content = extract_article_content(response.text, response.url)
        if not content:
            LOGGER.warning("No article content extracted for %s", response.url)
            return

        text_path = raw_dir / f"{safe_slug}_core_paragraphs.txt"
        text_output = render_content_to_text(content)
        text_path.write_text(text_output, encoding="utf-8")
        LOGGER.info("Saved core paragraphs to %s", text_path)

        soup = BeautifulSoup(response.text, "html.parser")

        yield {
            "source_url": response.url,
            "title": soup.title.string.strip() if soup.title else "",
            "raw_html_path": str(html_path.relative_to(project_path())),
            "core_paragraphs_path": str(text_path.relative_to(project_path())),
        }
