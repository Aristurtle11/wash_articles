from __future__ import annotations

import logging
import urllib.parse
from pathlib import Path
from typing import Any, Iterable, Iterator

from bs4 import BeautifulSoup

from ..core.base_spider import BaseSpider
from ..core.http_client import HttpRequest, HttpResponse
from ..settings import load_config, project_path
from ..utils.realtor_extract import (
    extract_article_content,
    render_content_to_text,
    download_images,
)


LOGGER = logging.getLogger(__name__)


class RealtorSpider(BaseSpider):
    name = "realtor"

    def __init__(self, client, pipelines=None, *, config=None):
        super().__init__(client, pipelines, config=config)
        app_config = load_config()
        self._raw_root = app_config.paths.raw_for(self.name)

    def start_requests(self) -> Iterable[HttpRequest]:
        yield HttpRequest(url=self.config["start_url"])

    def parse(self, response: HttpResponse) -> Iterator[Any]:
        LOGGER.info(
            "Parsing response from %s (status=%s, body=%d bytes)",
            response.url,
            response.status,
            len(response.body),
        )
        raw_dir = self._raw_root
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

        image_dir = raw_dir / "images"
        image_results = download_images(
            [entry for entry in content if entry.get("kind") == "image"],
            cookie_jar_path=self.client.cookie_path,
            dest_dir=image_dir,
        )
        LOGGER.info(
            "Downloaded %d images for %s",
            sum(1 for item in image_results if item.get("path")),
            response.url,
        )

        serialized_images: list[dict[str, Any]] = []
        for img in image_results:
            path = img.get("path")
            if isinstance(path, Path):
                relative = path.relative_to(project_path())
                serialized_images.append({**img, "path": str(relative)})
            elif path is None:
                serialized_images.append(img)
            else:
                try:
                    relative = Path(path).relative_to(project_path())
                    serialized_images.append({**img, "path": str(relative)})
                except ValueError:
                    serialized_images.append(img)

        soup = BeautifulSoup(response.text, "html.parser")

        yield {
            "source_url": response.url,
            "title": soup.title.string.strip() if soup.title else "",
            "raw_html_path": str(html_path.relative_to(project_path())),
            "core_paragraphs_path": str(text_path.relative_to(project_path())),
            "images": serialized_images,
        }
