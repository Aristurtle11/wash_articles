"""High-level orchestration for publishing translated content."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

from src.platforms import ContentBundle, ContentPublisher, MediaUploadResult, MediaUploader


class PublishingService:
    """Coordinates filesystem discovery and platform publishing."""

    def __init__(self, publisher: ContentPublisher, media_uploader: MediaUploader | None = None) -> None:
        self._publisher = publisher
        self._media_uploader = media_uploader

    def discover_bundles(self, translated_root: Path, raw_root: Path) -> Iterable[ContentBundle]:
        """Yield bundles by matching translated articles to image folders."""
        _ = (translated_root, raw_root)
        # TODO: Implement discovery logic based on channel tokens.
        yield from ()

    def upload_media(self, bundle: ContentBundle) -> Sequence[MediaUploadResult]:
        """Upload related media and return ordered URLs."""
        if not self._media_uploader:
            raise RuntimeError("未配置媒体上传器，无法上传图片")
        results = list(self._media_uploader.upload_batch(bundle))
        return results

    def replace_placeholders(self, article_path: Path, uploads: Sequence[MediaUploadResult]) -> str:
        """Inject media URLs into article placeholders and return the new body."""
        _ = (article_path, uploads)
        # TODO: Mutate article content and persist to disk.
        return ""

    def publish(self, bundle: ContentBundle) -> str:
        """Publish a single bundle through the configured platform."""
        self._publisher.prepare()
        return self._publisher.publish(bundle)
