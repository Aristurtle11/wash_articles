"""Helper functions for the publishing workflow."""

from __future__ import annotations

from pathlib import Path
import sys

from src.ai.title_generator import TitleConfig, TitleGenerator
from src.settings import AppConfig


def select_article(translated_root: Path) -> Path:
    """Selects the latest translated article from a directory."""
    if not translated_root.is_dir():
        raise FileNotFoundError(f"未找到翻译文章目录: {translated_root}")
    candidates = sorted(
        translated_root.glob("*.translated.txt"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(f"目录 {translated_root} 中未发现文章文件")
    return candidates[0]


def collect_images(raw_root: Path) -> list[Path]:
    """Collects all image files from the specified raw data directory."""
    image_dir = raw_root / "images"
    if not image_dir.is_dir():
        raise FileNotFoundError(f"未找到图片目录: {image_dir}")
    images = sorted(
        p for p in image_dir.iterdir() if p.is_file() and p.name.lower().startswith("image_")
    )
    if not images:
        raise FileNotFoundError(f"目录 {image_dir} 中未找到任何 image_* 文件")
    return images


def derive_title_from_path(article_path: Path) -> str:
    """Creates a default title from the article's filename."""
    stem = article_path.stem.replace(".translated", "")
    return stem.replace("_", " ").replace("-", " ").strip().title()


def generate_ai_title(
    article_path: Path,
    translated_root: Path,
    channel: str,
    app_config: AppConfig,
) -> str:
    """Generate or reuse an AI-crafted Chinese title for the article."""
    title_config = TitleConfig.from_app_config(channel=channel, app_config=app_config)
    generator = TitleGenerator.from_config(
        config=title_config,
        relative_to=translated_root,
    )
    title_path = generator.generate_title_file(article_path)
    return title_path.read_text(encoding="utf-8").strip()


def resolve_title(
    article_path: Path,
    translated_root: Path,
    channel: str,
    app_config: AppConfig,
    *,
    override: str | None,
) -> str:
    """
    Resolves the final article title.

    Priority:
    1.  An explicit override from the command line.
    2.  A previously AI-generated title file.
    3.  A fallback title derived from the filename.
    """
    if override:
        return override.strip()

    try:
        ai_title = generate_ai_title(article_path, translated_root, channel, app_config)
        if ai_title:
            return ai_title
    except Exception as exc:
        print(f"AI 标题生成失败，将使用默认标题: {exc}", file=sys.stderr)

    return derive_title_from_path(article_path)
