"""Workflow for uploading complete WeChat articles."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

try:
    from markdown import markdown
except ModuleNotFoundError as exc:  # pragma: no cover - import guard
    raise RuntimeError(
        "缺少 markdown 库，请先执行 'pip install markdown' 或安装项目依赖。"
    ) from exc

from src.platforms import ContentBundle, MediaUploadResult
from src.platforms.wechat import WeChatApiError, WeChatDraftClient, WeChatMediaUploader


_PLACEHOLDER_PATTERN = re.compile(r"{{\s*\[Image\s+(\d+)\]\s*}}", re.IGNORECASE)


@dataclass(slots=True)
class ArticleMetadata:
    """Metadata required to publish a single WeChat article."""

    channel: str
    article_path: Path
    title: str
    author: str | None = None
    digest: str | None = None
    source_url: str | None = None
    need_open_comment: bool = False
    only_fans_can_comment: bool = False


@dataclass(slots=True)
class ArticleResult:
    """Outcome of a publishing attempt."""

    media_id: str
    payload: dict[str, object]
    uploads: list[MediaUploadResult]
    markdown_path: Path


class WeChatArticleWorkflow:
    """Coordinates image upload, placeholder replacement, and draft submission."""

    def __init__(
        self,
        media_uploader: WeChatMediaUploader,
        draft_client: WeChatDraftClient,
    ) -> None:
        self._media_uploader = media_uploader
        self._draft_client = draft_client

    def publish(
        self,
        bundle: ContentBundle,
        metadata: ArticleMetadata,
        *,
        dry_run: bool = False,
    ) -> ArticleResult:
        uploads = list(self._media_uploader.upload_batch(bundle))
        if not uploads:
            raise RuntimeError("未找到需要上传的图片文件")

        markdown_content = self._replace_placeholders(metadata.article_path, uploads)
        html_content = self._markdown_to_html(markdown_content)

        payload = self._build_payload(metadata, uploads, markdown_content, html_content)

        if dry_run:
            response = {"media_id": "<dry-run>", "payload_preview": payload}
        else:
            response = self._draft_client.create_draft(payload)

        media_id = response.get("media_id", "")
        if not media_id:
            raise WeChatApiError(
                "草稿创建未返回 media_id",
                details=response,
            )

        return ArticleResult(
            media_id=media_id,
            payload=payload,
            uploads=uploads,
            markdown_path=metadata.article_path,
        )

    def _replace_placeholders(
        self,
        article_path: Path,
        uploads: Sequence[MediaUploadResult],
    ) -> str:
        text = article_path.read_text(encoding="utf-8")
        matches = list(_PLACEHOLDER_PATTERN.finditer(text))
        uploads_sorted = sorted(uploads, key=lambda item: item.order)

        if len(matches) > len(uploads_sorted):
            raise RuntimeError(
                f"文章中的图片占位符数量({len(matches)})超过上传的图片数量({len(uploads_sorted)})"
            )

        def replacement(match: re.Match[str]) -> str:
            index = int(match.group(1))
            try:
                upload = uploads_sorted[index - 1]
            except IndexError as exc:
                raise RuntimeError(
                    f"占位符索引 {index} 超出上传图片数量 {len(uploads_sorted)}"
                ) from exc
            alt = f"Image {index}"
            return f"![{alt}]({upload.remote_url})"

        updated = _PLACEHOLDER_PATTERN.sub(replacement, text)

        # Append any extra images that were uploaded but not referenced.
        if len(uploads_sorted) > len(matches):
            extras = uploads_sorted[len(matches) :]
            extra_lines = [""]
            for item in extras:
                extra_lines.append(f"![Image {item.order}]({item.remote_url})")
            updated = updated.rstrip() + "\n\n" + "\n".join(extra_lines) + "\n"

        article_path.write_text(updated, encoding="utf-8")
        return updated

    def _markdown_to_html(self, markdown_text: str) -> str:
        html = markdown(markdown_text, extensions=["extra"])  # type: ignore[arg-type]
        return html

    def _build_payload(
        self,
        metadata: ArticleMetadata,
        uploads: Sequence[MediaUploadResult],
        markdown_content: str,
        content_html: str,
    ) -> dict[str, object]:
        thumbnail_id = uploads[0].media_id
        if not thumbnail_id:
            raise RuntimeError("首张图片缺少 media_id，无法作为封面")

        article = {
            "article_type": "news",
            "title": metadata.title,
            "content": content_html,
            "thumb_media_id": thumbnail_id,
            "need_open_comment": 1 if metadata.need_open_comment else 0,
            "only_fans_can_comment": 1 if metadata.only_fans_can_comment else 0,
        }
        if metadata.author:
            article["author"] = metadata.author
        digest = metadata.digest or self._build_digest(markdown_content)
        if digest:
            article["digest"] = digest
        if metadata.source_url:
            article["content_source_url"] = metadata.source_url

        return {"articles": [article]}

    def _build_digest(self, markdown_content: str) -> str:
        text = _PLACEHOLDER_PATTERN.sub("", markdown_content)
        # Strip Markdown image syntax while keeping alt text.
        text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
        cleaned = " ".join(line.strip() for line in text.splitlines() if line.strip())
        return cleaned[:120]
