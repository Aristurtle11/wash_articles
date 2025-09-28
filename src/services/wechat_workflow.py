"""Workflow for uploading complete WeChat articles."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

try:
    from markdown import markdown
except ModuleNotFoundError as exc:  # pragma: no cover - import guard
    raise RuntimeError(
        "缺少 markdown 库，请先执行 'pip install markdown' 或安装项目依赖。"
    ) from exc

from src.platforms import ContentBundle, MediaUploadResult
from src.platforms.wechat import WeChatApiError, WeChatDraftClient, WeChatMediaUploader


_PLACEHOLDER_PATTERN = re.compile(r"{{\s*\[Image\s+(\d+)\]\s*}}", re.IGNORECASE)
_MARKDOWN_IMAGE_PATTERN = re.compile(r"!\[Image\s+(\d+)\]\([^\)]+\)", re.IGNORECASE)


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
        uploads = self._collect_uploads(bundle, dry_run=dry_run)
        if not uploads:
            raise RuntimeError("未找到需要上传的图片文件")

        html_content = self._build_html_content(
            metadata.article_path,
            uploads,
            persist=not dry_run,
        )

        payload = self._build_payload(metadata, uploads, html_content)

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

    def _build_html_content(
        self,
        article_path: Path,
        uploads: Sequence[MediaUploadResult],
        *,
        persist: bool,
    ) -> str:
        formatted_path = article_path.with_suffix(".formatted.html")
        uploads_sorted = sorted(uploads, key=lambda item: item.order)

        if formatted_path.exists():
            html = formatted_path.read_text(encoding="utf-8")
            updated = self._inject_images_html(html, uploads_sorted)
            if persist and updated != html:
                formatted_path.write_text(updated, encoding="utf-8")
            return updated

        markdown_content = self._prepare_markdown(
            article_path,
            uploads_sorted,
            persist=persist,
        )
        return self._markdown_to_html(markdown_content)

    def _prepare_markdown(
        self,
        article_path: Path,
        uploads: Sequence[MediaUploadResult],
        *,
        persist: bool,
    ) -> str:
        text = article_path.read_text(encoding="utf-8")
        uploads_sorted = sorted(uploads, key=lambda item: item.order)

        updated, changed = self._inject_images(text, uploads_sorted)

        if persist and changed:
            article_path.write_text(updated, encoding="utf-8")
        return updated

    def _inject_images(
        self,
        text: str,
        uploads_sorted: Sequence[MediaUploadResult],
    ) -> tuple[str, bool]:
        matches = list(_PLACEHOLDER_PATTERN.finditer(text))

        if matches:
            updated = self._replace_placeholder_matches(text, matches, uploads_sorted)
            updated = self._append_extra_images(updated, uploads_sorted, start_index=len(matches))
            return updated, updated != text

        # No placeholders remain; update existing markdown image tags.
        def markdown_replacement(match: re.Match[str]) -> str:
            index = int(match.group(1))
            try:
                upload = uploads_sorted[index - 1]
            except IndexError:
                return match.group(0)
            alt = f"Image {index}"
            return f"![{alt}]({upload.remote_url})"

        updated, count = _MARKDOWN_IMAGE_PATTERN.subn(markdown_replacement, text)
        if count:
            return updated, updated != text

        # Nothing to replace; optionally append images once.
        updated = self._append_extra_images(text, uploads_sorted, start_index=0)
        return updated, updated != text

    def _replace_placeholder_matches(
        self,
        text: str,
        matches: Sequence[re.Match[str]],
        uploads_sorted: Sequence[MediaUploadResult],
    ) -> str:
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

        return _PLACEHOLDER_PATTERN.sub(replacement, text)

    def _append_extra_images(
        self,
        text: str,
        uploads_sorted: Sequence[MediaUploadResult],
        *,
        start_index: int,
    ) -> str:
        if start_index >= len(uploads_sorted):
            return text

        extra_lines = [""]
        for item in uploads_sorted[start_index:]:
            extra_lines.append(f"![Image {item.order}]({item.remote_url})")
        return text.rstrip() + "\n\n" + "\n".join(extra_lines) + "\n"

    def _inject_images_html(
        self,
        html: str,
        uploads_sorted: Sequence[MediaUploadResult],
    ) -> str:
        matches = list(_PLACEHOLDER_PATTERN.finditer(html))

        def replacement(match: re.Match[str]) -> str:
            index = int(match.group(1))
            try:
                upload = uploads_sorted[index - 1]
            except IndexError as exc:
                raise RuntimeError(
                    f"占位符索引 {index} 超出上传图片数量 {len(uploads_sorted)}"
                ) from exc
            return self._render_image_block(upload, index)

        updated = _PLACEHOLDER_PATTERN.sub(replacement, html)

        if len(uploads_sorted) > len(matches):
            extras = uploads_sorted[len(matches) :]
            extra_blocks = "\n".join(
                self._render_image_block(item, item.order) for item in extras
            )
            insertion = f"\n{extra_blocks}\n"
            if "</body>" in updated:
                updated = updated.replace("</body>", f"{insertion}</body>")
            else:
                updated = updated.rstrip() + insertion
        return updated

    def _render_image_block(self, upload: MediaUploadResult, index: int) -> str:
        alt = f"Image {index}"
        return (
            f'<figure class="article-image" data-index="{index}">'
            f"<img src=\"{upload.remote_url}\" alt=\"{alt}\" />"
            "</figure>"
        )

    def _markdown_to_html(self, markdown_text: str) -> str:
        html = markdown(markdown_text, extensions=["extra"])  # type: ignore[arg-type]
        return html

    def _build_payload(
        self,
        metadata: ArticleMetadata,
        uploads: Sequence[MediaUploadResult],
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
        digest = self._prepare_digest(metadata.digest)
        if digest:
            article["digest"] = digest
        if metadata.source_url:
            article["content_source_url"] = metadata.source_url

        return {"articles": [article]}

    def _prepare_digest(self, digest: str | None) -> str | None:
        if not digest:
            return None
        return self._truncate_utf8(digest, max_bytes=256)

    def _truncate_utf8(self, text: str, *, max_bytes: int) -> str:
        encoded = text.encode("utf-8")
        if len(encoded) <= max_bytes:
            return text
        truncated = encoded[:max_bytes]
        # Ensure no partial multibyte character at the end.
        while truncated and (truncated[-1] & 0xC0) == 0x80:
            truncated = truncated[:-1]
        return truncated.decode("utf-8", errors="ignore")
