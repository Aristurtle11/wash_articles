"""Spider registry."""

from __future__ import annotations

from typing import Dict, Type

from .example_spider import ExampleSpider
from ..core.base_spider import BaseSpider

SPIDER_REGISTRY: Dict[str, Type[BaseSpider]] = {
    ExampleSpider.name: ExampleSpider,
}


def get_spider(name: str) -> Type[BaseSpider]:
    try:
        return SPIDER_REGISTRY[name]
    except KeyError as exc:
        raise KeyError(f"Unknown spider '{name}'. Registered: {list(SPIDER_REGISTRY)}") from exc


__all__ = ["SPIDER_REGISTRY", "get_spider", "ExampleSpider"]
