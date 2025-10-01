"""Data models for the WeChat article publishing workflow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.platforms import MediaUploadResult


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
