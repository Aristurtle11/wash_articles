"""Skeleton implementation for WeChat media uploads."""

from __future__ import annotations

from typing import Iterable

from src.platforms.base import ContentBundle, MediaUploadResult, MediaUploader
class WeChatMediaUploader(MediaUploader):
    """Uploads article images to WeChat."""

    def __init__(self) -> None:
        # TODO: Inject HTTP client, token provider, etc.
        pass

    def upload_batch(self, bundle: ContentBundle) -> Iterable[MediaUploadResult]:
        """Upload images for the bundle (placeholder implementation)."""
        _ = bundle
        # TODO: Integrate with WeChat upload API.
        yield from ()
