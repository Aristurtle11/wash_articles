"""Workflow for uploading complete WeChat articles."""

from __future__ import annotations

from typing import Iterable

from src.platforms import ContentBundle, MediaUploadResult
from src.platforms.wechat import WeChatApiError, WeChatDraftClient, WeChatMediaUploader
from src.services.wechat_components import ContentBuilder, PayloadBuilder
from src.services.wechat_models import ArticleMetadata, ArticleResult


class WeChatArticleWorkflow:
    """Coordinates image upload, placeholder replacement, and draft submission."""

    def __init__(
        self,
        media_uploader: WeChatMediaUploader,
        draft_client: WeChatDraftClient,
        content_builder: ContentBuilder,
        payload_builder: PayloadBuilder,
    ) -> None:
        self._media_uploader = media_uploader
        self._draft_client = draft_client
        self._content_builder = content_builder
        self._payload_builder = payload_builder

    def publish(
        self,
        bundle: ContentBundle,
        metadata: ArticleMetadata,
        *,
        dry_run: bool = False,
    ) -> ArticleResult:
        uploads = self._collect_uploads(bundle, dry_run=dry_run)
        if not uploads:
            raise RuntimeError("未找到需要上传的图片文件")

        html_content = self._content_builder.build(
            metadata.article_path,
            uploads,
            persist=not dry_run,
        )

        payload = self._payload_builder.build(metadata, uploads, html_content)

        if dry_run:
            media_id = "<dry-run>"
        else:
            response = self._draft_client.create_draft(payload)
            media_id = response.get("media_id", "")
            if not media_id:
                raise WeChatApiError("草稿创建未返回 media_id", details=response)

        return ArticleResult(
            media_id=media_id,
            payload=payload,
            uploads=uploads,
            markdown_path=metadata.article_path,
        )

    def _collect_uploads(
        self,
        bundle: ContentBundle,
        *,
        dry_run: bool,
    ) -> list[MediaUploadResult]:
        if dry_run:
            return list(self._simulate_uploads(bundle))
        return list(self._media_uploader.upload_batch(bundle))

    def _simulate_uploads(self, bundle: ContentBundle) -> Iterable[MediaUploadResult]:
        images = sorted(
            (path for path in bundle.images if path.is_file()),
            key=lambda path: path.name,
        )
        for order, path in enumerate(images, start=1):
            yield MediaUploadResult(
                local_path=path,
                remote_url=path.as_uri(),
                order=order,
                media_id=f"<dry-run:{path.stem}>",
            )
