"""Components for the WeChat article publishing workflow."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Sequence

try:
    from markdown import markdown
except ModuleNotFoundError as exc:
    raise RuntimeError(
        "缺少 markdown 库，请先执行 'pip install markdown' 或安装项目依赖。"
    ) from exc

from src.platforms import MediaUploadResult
from src.services.wechat_models import ArticleMetadata


_PLACEHOLDER_PATTERN = re.compile(r"{{\s*\[Image\s+(\d+)\]\s*}}", re.IGNORECASE)
_HTML_PLACEHOLDER_PATTERN = re.compile(
    r"<p[^>]*>\s*(?:{{\s*\[Image\s+(\d+)\]\s*}}|\[\[IMAGE_(\d+)\]\])\s*</p>",
    re.IGNORECASE,
)
_BRACKET_PLACEHOLDER_PATTERN = re.compile(r"\[\[IMAGE_(\d+)\]\]", re.IGNORECASE)
_MARKDOWN_IMAGE_PATTERN = re.compile(r"!\[Image\s+(\d+)\]\([^\)]+\)", re.IGNORECASE)


class ContentBuilder:
    """Builds the final HTML content for a WeChat article."""

    def build(
        self,
        article_path: Path,
        uploads: Sequence[MediaUploadResult],
        *,
        persist: bool,
    ) -> str:
        """
        Builds the HTML content by injecting image URLs into the source file.

        It first looks for a pre-formatted `.formatted.html` file. If found,
        it uses that. Otherwise, it falls back to the original text file
        (presumably Markdown) and converts it to HTML.

        Args:
            article_path: Path to the source article file (.txt or .md).
            uploads: A sequence of successfully uploaded media items.
            persist: If True, modifications (like image URL injection) are
                     saved back to the source files.

        Returns:
            The final HTML content string.
        """
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
        if _BRACKET_PLACEHOLDER_PATTERN.search(text):
            text = _BRACKET_PLACEHOLDER_PATTERN.sub(
                lambda match: f"{{{{[Image {match.group(1)}]}}}}", text
            )

        matches = list(_PLACEHOLDER_PATTERN.finditer(text))

        if matches:
            updated = self._replace_placeholder_matches(text, matches, uploads_sorted)
            updated = self._append_extra_images(updated, uploads_sorted, start_index=len(matches))
            updated, replaced_count = self._replace_markdown_images(updated, uploads_sorted)
            changed = updated != text or replaced_count > 0
            return updated, changed

        updated, count = self._replace_markdown_images(text, uploads_sorted)
        if count:
            return updated, updated != text

        updated = self._append_extra_images(text, uploads_sorted, start_index=0)
        return updated, updated != text

    def _replace_markdown_images(
        self, text: str, uploads_sorted: Sequence[MediaUploadResult]
    ) -> tuple[str, int]:
        def markdown_replacement(match: re.Match[str]) -> str:
            index = int(match.group(1))
            try:
                upload = uploads_sorted[index - 1]
            except IndexError:
                return match.group(0)
            alt = f"Image {index}"
            return f"![{alt}]({upload.remote_url})"

        return _MARKDOWN_IMAGE_PATTERN.subn(markdown_replacement, text)

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
        matches = list(_HTML_PLACEHOLDER_PATTERN.finditer(html))

        def replacement(match: re.Match[str]) -> str:
            index_str = match.group(1) or match.group(2)
            index = int(index_str)
            try:
                upload = uploads_sorted[index - 1]
            except IndexError as exc:
                raise RuntimeError(
                    f"占位符索引 {index} 超出上传图片数量 {len(uploads_sorted)}"
                ) from exc
            return self._render_image_block(upload, index)

        updated = _HTML_PLACEHOLDER_PATTERN.sub(replacement, html)
        replaced_count = len(matches)

        bare_matches = list(_BRACKET_PLACEHOLDER_PATTERN.finditer(updated))

        def bare_replacement(match: re.Match[str]) -> str:
            index = int(match.group(1))
            try:
                upload = uploads_sorted[index - 1]
            except IndexError as exc:
                raise RuntimeError(
                    f"占位符索引 {index} 超出上传图片数量 {len(uploads_sorted)}"
                ) from exc
            return self._render_image_block(upload, index)

        if bare_matches:
            updated = _BRACKET_PLACEHOLDER_PATTERN.sub(bare_replacement, updated)
            replaced_count = max(replaced_count, len(bare_matches))

        if len(uploads_sorted) > replaced_count:
            extras = uploads_sorted[replaced_count:]
            extra_blocks = "\n".join(self._render_image_block(item, item.order) for item in extras)
            insertion = f"\n{extra_blocks}\n"
            if "</body>" in updated:
                updated = updated.replace("</body>", f"{insertion}</body>")
            else:
                updated = updated.rstrip() + insertion
        return updated

    def _render_image_block(self, upload: MediaUploadResult, index: int) -> str:
        alt = f"Image {index}"
        return (
            '<p style="text-align:center; margin:1.5em 0;">'
            f'<img src="{upload.remote_url}" alt="{alt}" '
            'style="max-width:100%; border-radius:8px; box-shadow:0 4px 6px rgba(0,0,0,0.15);" />'
            "</p>"
        )

    def _markdown_to_html(self, markdown_text: str) -> str:
        return markdown(markdown_text, extensions=["extra"])


class PayloadBuilder:
    """Builds the JSON payload for the WeChat Draft API."""

    def build(
        self,
        metadata: ArticleMetadata,
        uploads: Sequence[MediaUploadResult],
        content_html: str,
    ) -> dict[str, object]:
        """
        Builds the payload dictionary.

        Args:
            metadata: Article metadata (title, author, etc.).
            uploads: A sequence of successfully uploaded media items.
            content_html: The final HTML content of the article.

        Returns:
            A dictionary formatted for the WeChat `draft/add` endpoint.
        """
        if not uploads:
            raise ValueError("At least one image upload is required to select a thumbnail.")

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
        while truncated and (truncated[-1] & 0xC0) == 0x80:
            truncated = truncated[:-1]
        return truncated.decode("utf-8", errors="ignore")
