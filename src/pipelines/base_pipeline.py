"""Pipeline contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BasePipeline(ABC):
    """Interface for processing scraped items."""

    @abstractmethod
    def process_item(self, item: Any) -> Any:
        """Handle an individual item and return the next stage payload."""


class PipelineManager:
    """Apply pipelines in order."""

    def __init__(self, *pipelines: BasePipeline) -> None:
        self._pipelines = list(pipelines)

    def __iter__(self):
        return iter(self._pipelines)

    def run(self, item: Any) -> Any:
        payload = item
        for pipeline in self._pipelines:
            payload = pipeline.process_item(payload)
        return payload
