"""Abstract spider contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Iterable, Iterator, Sequence

from .http_client import HttpClient, HttpRequest, HttpResponse
from ..pipelines.base_pipeline import BasePipeline, PipelineManager


class BaseSpider(ABC):
    name: str = "base"

    def __init__(
        self,
        client: HttpClient,
        pipelines: Sequence[BasePipeline] | None = None,
        *,
        config: dict[str, str] | None = None,
    ) -> None:
        self.client = client
        self.config = config or {}
        self._pipeline_manager = PipelineManager(*(pipelines or ()))

    def run(self) -> None:
        self.prepare()
        for request in self.start_requests():
            response = self.client.fetch(request)
            for item in self.parse(response):
                processed = self._pipeline_manager.run(item)
                self.handle_item(processed)

    def prepare(self) -> None:
        """Hook executed once before the crawl starts."""

    @abstractmethod
    def start_requests(self) -> Iterable[HttpRequest]:
        """Yield the initial requests."""

    @abstractmethod
    def parse(self, response: HttpResponse) -> Iterator[Any]:
        """Convert a response into domain items."""

    def handle_item(self, item: Any) -> None:
        """Default item handler; subclasses may override to collect stats or emit events."""
        _ = item
