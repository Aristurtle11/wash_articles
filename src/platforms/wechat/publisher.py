"""Skeleton WeChat content publisher."""

from __future__ import annotations

from src.platforms.base import ContentBundle, ContentPublisher
from src.platforms.wechat.credentials import WeChatCredentialStore
from src.platforms.wechat.media import WeChatMediaUploader


class WeChatContentPublisher(ContentPublisher):
    """Coordinates WeChat-specific publishing steps."""

    def __init__(
        self,
        credential_store: WeChatCredentialStore,
        media_uploader: WeChatMediaUploader,
    ) -> None:
        self._credentials = credential_store
        self._media_uploader = media_uploader

    def prepare(self) -> None:
        """Validate credentials and ensure token availability."""
        _ = self._credentials.load_app_id()
        _ = self._credentials.load_app_secret()
        # TODO: Warm token cache and verify connectivity.

    def publish(self, bundle: ContentBundle) -> str:
        """Publish the content bundle to WeChat (placeholder)."""
        _ = bundle
        # TODO: Implement media upload, placeholder replacement, and article submission.
        return ""
