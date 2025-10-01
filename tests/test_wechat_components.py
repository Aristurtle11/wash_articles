"""Unit tests for WeChat publishing components."""

from __future__ import annotations

from pathlib import Path
import pytest

from src.platforms import MediaUploadResult
from src.services.wechat_components import ContentBuilder, PayloadBuilder
from src.services.wechat_models import ArticleMetadata


@pytest.fixture
def sample_uploads() -> list[MediaUploadResult]:
    """Provides a list of sample media upload results."""
    return [
        MediaUploadResult(
            local_path=Path("images/image_1.jpg"),
            remote_url="https://wechat.com/img/1",
            order=1,
            media_id="media_id_1",
        ),
        MediaUploadResult(
            local_path=Path("images/image_2.png"),
            remote_url="https://wechat.com/img/2",
            order=2,
            media_id="media_id_2",
        ),
    ]


@pytest.fixture
def article_metadata(tmp_path: Path) -> ArticleMetadata:
    """Provides a sample ArticleMetadata instance."""
    article_path = tmp_path / "test_article.txt"
    article_path.touch()
    return ArticleMetadata(
        channel="test_channel",
        article_path=article_path,
        title="测试标题",
        author="测试作者",
        digest="这是一个摘要",
        source_url="https://example.com/source",
        need_open_comment=True,
        only_fans_can_comment=True,
    )


class TestContentBuilder:
    """Tests for the ContentBuilder component."""

    def test_build_with_formatted_html(
        self, tmp_path: Path, sample_uploads: list[MediaUploadResult]
    ):
        """Verify it correctly injects images into a pre-formatted HTML file."""
        builder = ContentBuilder()
        article_path = tmp_path / "my_article.txt"
        formatted_path = tmp_path / "my_article.formatted.html"
        formatted_path.write_text(
            "<h1>Hello</h1><p>{{[Image 1]}}</p><p>Some text</p><p>[[IMAGE_2]]</p>",
            encoding="utf-8",
        )

        html = builder.build(article_path, sample_uploads, persist=False)

        assert '<img src="https://wechat.com/img/1"' in html
        assert '<img src="https://wechat.com/img/2"' in html
        assert "<h1>Hello</h1>" in html

    def test_build_with_markdown(self, tmp_path: Path, sample_uploads: list[MediaUploadResult]):
        """Verify it converts Markdown and injects images correctly."""
        builder = ContentBuilder()
        article_path = tmp_path / "my_article.txt"
        article_path.write_text(
            "# Hello\n\n{{[Image 1]}}\n\nSome text\n\n![Image 2](placeholder.jpg)",
            encoding="utf-8",
        )

        html = builder.build(article_path, sample_uploads, persist=False)

        assert "<h1>Hello</h1>" in html
        assert '<img src="https://wechat.com/img/1"' in html
        # The original markdown image tag should be updated
        assert '<img src="https://wechat.com/img/2"' in html
        assert "placeholder.jpg" not in html

    def test_append_extra_images(self, tmp_path: Path, sample_uploads: list[MediaUploadResult]):
        """Verify it appends images that are not referenced by placeholders."""
        builder = ContentBuilder()
        article_path = tmp_path / "my_article.txt"
        article_path.write_text("# Hello\n\nJust text, no placeholders.", encoding="utf-8")

        html = builder.build(article_path, sample_uploads, persist=False)

        assert "<h1>Hello</h1>" in html
        assert '<img src="https://wechat.com/img/1"' in html
        assert '<img src="https://wechat.com/img/2"' in html

    def test_persist_changes(self, tmp_path: Path, sample_uploads: list[MediaUploadResult]):
        """Verify `persist=True` saves the updated content back to the file."""
        builder = ContentBuilder()
        article_path = tmp_path / "my_article.txt"
        article_path.write_text("{{[Image 1]}}", encoding="utf-8")

        builder.build(article_path, sample_uploads, persist=True)

        updated_content = article_path.read_text(encoding="utf-8")
        assert "![Image 1](https://wechat.com/img/1)" in updated_content


class TestPayloadBuilder:
    """Tests for the PayloadBuilder component."""

    def test_build_full_payload(
        self,
        article_metadata: ArticleMetadata,
        sample_uploads: list[MediaUploadResult],
    ):
        """Verify it constructs a complete payload with all fields."""
        builder = PayloadBuilder()
        html_content = "<h1>Hello World</h1>"

        payload = builder.build(article_metadata, sample_uploads, html_content)
        article = payload["articles"][0]

        assert article["title"] == "测试标题"
        assert article["author"] == "测试作者"
        assert article["digest"] == "这是一个摘要"
        assert article["content_source_url"] == "https://example.com/source"
        assert article["content"] == html_content
        assert article["thumb_media_id"] == "media_id_1"
        assert article["need_open_comment"] == 1
        assert article["only_fans_can_comment"] == 1

    def test_build_minimal_payload(
        self,
        article_metadata: ArticleMetadata,
        sample_uploads: list[MediaUploadResult],
    ):
        """Verify it constructs a payload with only the required fields."""
        builder = PayloadBuilder()
        # Create a minimal metadata object
        metadata = ArticleMetadata(
            channel="test",
            article_path=article_metadata.article_path,
            title="Minimal Title",
        )
        html_content = "<p>Minimal</p>"

        payload = builder.build(metadata, sample_uploads, html_content)
        article = payload["articles"][0]

        assert article["title"] == "Minimal Title"
        assert article["content"] == html_content
        assert article["thumb_media_id"] == "media_id_1"
        assert "author" not in article
        assert "digest" not in article
        assert "content_source_url" not in article
        assert article["need_open_comment"] == 0
        assert article["only_fans_can_comment"] == 0

    def test_build_raises_error_if_no_uploads(self, article_metadata: ArticleMetadata):
        """Verify it raises an error when the upload list is empty."""
        builder = PayloadBuilder()
        with pytest.raises(ValueError, match="At least one image upload is required"):
            builder.build(article_metadata, [], "html")

    def test_digest_truncation(
        self,
        article_metadata: ArticleMetadata,
        sample_uploads: list[MediaUploadResult],
    ):
        """Verify it correctly truncates a long digest."""
        builder = PayloadBuilder()
        long_digest = "a" * 300
        article_metadata.digest = long_digest

        payload = builder.build(article_metadata, sample_uploads, "")
        digest = payload["articles"][0]["digest"]

        assert len(digest.encode("utf-8")) <= 256
        assert digest.startswith("a")
