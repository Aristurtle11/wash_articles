from __future__ import annotations

from pathlib import Path

from src.platforms import ContentBundle, MediaUploadResult
from src.services.wechat_workflow import ArticleMetadata, WeChatArticleWorkflow


class StubUploader:
    def __init__(
        self, results: list[MediaUploadResult] | None = None, *, fail: bool = False
    ) -> None:
        self._results = results or []
        self.fail = fail
        self.called = False

    def upload_batch(self, bundle: ContentBundle):  # pragma: no cover - interface compliance
        self.called = True
        if self.fail:
            raise AssertionError("upload_batch should not be called during dry-run")
        return list(self._results)


class StubDraftClient:
    def __init__(self) -> None:
        self.called = False
        self.payload = None

    def create_draft(
        self, payload: dict[str, object]
    ) -> dict[str, object]:  # pragma: no cover - interface compliance
        self.called = True
        self.payload = payload
        return {"media_id": "MEDIA_ID"}


def _media_result(path: Path, url: str, order: int) -> MediaUploadResult:
    return MediaUploadResult(
        local_path=path, remote_url=url, order=order, media_id=f"MEDIA_{order}"
    )


def test_prepare_markdown_updates_placeholders_and_persists(tmp_path: Path) -> None:
    article_path = tmp_path / "article.txt"
    article_path.write_text("开头\n\n{{[Image 1]}}\n\n结尾\n", encoding="utf-8")
    image1 = tmp_path / "image_001.jpg"
    image1.write_bytes(b"")
    image2 = tmp_path / "image_002.jpg"
    image2.write_bytes(b"")

    uploads = [
        _media_result(image1, "http://example.com/1.jpg", 1),
        _media_result(image2, "http://example.com/2.jpg", 2),
    ]

    workflow = WeChatArticleWorkflow(StubUploader(uploads), StubDraftClient())
    content = workflow._prepare_markdown(article_path, uploads, persist=True)

    assert "![Image 1](http://example.com/1.jpg)" in content
    assert content.count("![Image 1]") == 1
    assert article_path.read_text(encoding="utf-8").count("![Image 1]") == 1

    # 第二次更新应替换链接而非重复追加
    updated_uploads = [
        _media_result(image1, "http://example.com/new1.jpg", 1),
        _media_result(image2, "http://example.com/new2.jpg", 2),
    ]
    content_again = workflow._prepare_markdown(article_path, updated_uploads, persist=True)
    assert "http://example.com/new1.jpg" in content_again
    assert content_again.count("![Image 1]") == 1


def test_publish_dry_run_skips_network_and_preserves_file(tmp_path: Path) -> None:
    article_path = tmp_path / "article.txt"
    article_path.write_text("{{[Image 1]}}", encoding="utf-8")
    image_path = tmp_path / "image_001.jpg"
    image_path.write_bytes(b"")

    uploader = StubUploader(fail=True)
    draft_client = StubDraftClient()
    workflow = WeChatArticleWorkflow(uploader, draft_client)

    bundle = ContentBundle(channel="demo", article_path=article_path, images=[image_path])
    metadata = ArticleMetadata(channel="demo", article_path=article_path, title="Demo Title")

    result = workflow.publish(bundle, metadata, dry_run=True)

    assert result.media_id == "<dry-run>"
    assert not draft_client.called
    assert article_path.read_text(encoding="utf-8") == "{{[Image 1]}}"
    article = result.payload["articles"][0]
    assert article["thumb_media_id"].startswith("<dry-run:")


def test_build_html_content_prefers_formatted_file(tmp_path: Path) -> None:
    article_path = tmp_path / "article.translated.txt"
    article_path.write_text("正文段落\n", encoding="utf-8")
    formatted_path = article_path.with_suffix(".formatted.html")
    formatted_path.write_text(
        "<html><body><article>{{[Image 1]}}<p>正文段落</p></article></body></html>",
        encoding="utf-8",
    )

    image_path = tmp_path / "image_001.jpg"
    image_path.write_bytes(b"")
    upload = _media_result(image_path, "http://example.com/1.jpg", 1)

    workflow = WeChatArticleWorkflow(StubUploader([upload]), StubDraftClient())
    html = workflow._build_html_content(article_path, [upload], persist=False)

    assert "http://example.com/1.jpg" in html
    assert formatted_path.read_text(encoding="utf-8").count("http://example.com/1.jpg") == 0
