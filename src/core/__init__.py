"""Core primitives for web fetching."""

from .http_client import HttpClient, HttpRequest, HttpResponse
from .base_spider import BaseSpider

__all__ = [
    "HttpClient",
    "HttpRequest",
    "HttpResponse",
    "BaseSpider",
]
