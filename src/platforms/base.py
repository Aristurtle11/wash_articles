"""Base contracts for content publishing platforms."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Protocol, Sequence


@dataclass(slots=True)
class MediaUploadResult:
    """Represents the outcome of a single media upload."""

    local_path: Path
    remote_url: str
    order: int


@dataclass(slots=True)
class ContentBundle:
    """Groups article content with its related media assets."""

    channel: str
    article_path: Path
    images: Sequence[Path]


class MediaUploader(Protocol):
    """Uploads media assets to a remote platform."""

    def upload_batch(self, bundle: ContentBundle) -> Iterable[MediaUploadResult]:
        """Upload media for the given bundle and yield results in order."""


class ContentPublisher(ABC):
    """Publishes content bundles to a concrete platform."""

    @abstractmethod
    def prepare(self) -> None:
        """Execute pre-flight checks, e.g., credential validation."""

    @abstractmethod
    def publish(self, bundle: ContentBundle) -> str:
        """Publish the provided bundle and return a platform-specific identifier."""


class PlatformFactory(Protocol):
    """Factory interface for retrieving platform-specific publishers."""

    def create(self, platform: str) -> ContentPublisher:
        """Return a configured publisher for the selected platform."""
