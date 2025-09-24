from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Iterator

from bs4 import BeautifulSoup

from ..core.base_spider import BaseSpider
from ..core.http_client import HttpRequest, HttpResponse
from ..settings import project_path


class RealtorSpider(BaseSpider):
    name = "realtor"

    def start_requests(self) -> Iterable[HttpRequest]:
        yield HttpRequest(url=self.config["start_url"])

    def parse(self, response: HttpResponse) -> Iterator[Any]:
        soup = BeautifulSoup(response.text, "html.parser")
        body = soup.select_one("article") or soup.select_one("#content")
        if not body:
            return

        image_dir = project_path("data", "raw", self.name)
        image_dir.mkdir(parents=True, exist_ok=True)

        parts: list[str] = []
        images: list[dict[str, str]] = []
        counter = 1

        for element in body.children:
            if getattr(element, "name", None) == "img":
                src = element.get("data-src") or element.get("src")
                if not src:
                    continue
                img_id = f"{counter:02d}"
                filename = image_dir / f"image_{img_id}.jpg"
                img_resp = self.client.fetch(HttpRequest(url=src))
                filename.write_bytes(img_resp.body)
                parts.append(f"{{{{IMAGE {img_id}}}}}")
                images.append({"id": img_id, "src": src, "path": str(filename.relative_to(project_path()))})
                counter += 1
            elif getattr(element, "name", None) in {"p", "h1", "h2", "h3"}:
                text = element.get_text(strip=True)
                if text:
                    parts.append(text)

        yield {
            "source_url": response.url,
            "title": soup.title.string.strip() if soup.title else "",
            "content_with_placeholders": "\n\n".join(parts),
            "images": images,
        }
