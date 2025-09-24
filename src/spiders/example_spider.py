"""Example spider implementation."""

from __future__ import annotations

from typing import Any, Iterable, Iterator

from bs4 import BeautifulSoup

from ..core.base_spider import BaseSpider
from ..core.http_client import HttpRequest, HttpResponse


class ExampleSpider(BaseSpider):
    name = "example"

    def start_requests(self) -> Iterable[HttpRequest]:
        url = self.config.get("start_url", "https://example.com/")
        yield HttpRequest(url=url)

    def parse(self, response: HttpResponse) -> Iterator[Any]:
        soup = BeautifulSoup(response.text, "html.parser")
        title = soup.title.string.strip() if soup.title and soup.title.string else ""
        links = [a.get("href") for a in soup.select("a[href]")]
        yield {
            "source_url": response.url,
            "title": title,
            "link_count": len(links),
            "links": [link for link in links if link],
        }
