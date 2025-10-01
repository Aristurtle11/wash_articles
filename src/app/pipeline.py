"""Composable pipeline for fetch → translate → format → title → publish."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Sequence

from ..ai.formatter import Formatter, FormattingConfig
from ..ai.title_generator import TitleConfig, TitleGenerator
from ..ai.translator import TranslationConfig, Translator
from ..platforms import ContentBundle
from ..platforms.wechat import (
    WeChatApiClient,
    WeChatApiError,
    WeChatCredentialStore,
    WeChatDraftClient,
    WeChatMediaUploader,
)
from ..services.wechat_workflow import ArticleMetadata, WeChatArticleWorkflow
from ..settings import AppConfig, load_config
from ..utils.logging import get_logger
from .runner import run as run_spider

LOGGER = get_logger(__name__)


@dataclass(slots=True)
class PipelineContext:
    """Mutable context shared between pipeline steps."""

    config: AppConfig
    channel: str
    api_key: str | None = None
    overwrite: bool = False
    dry_run: bool = False
    translated_files: list[Path] = field(default_factory=list)
    formatted_files: list[Path] = field(default_factory=list)
    title_files: list[Path] = field(default_factory=list)

    @property
    def default_raw_root(self) -> Path:
        return self.config.paths.raw_for(self.channel)

    @property
    def translated_root(self) -> Path:
        return self.config.paths.translated_for(self.channel)

    @property
    def formatted_root(self) -> Path:
        return self.config.paths.formatted_for(self.channel)

    @property
    def titles_root(self) -> Path:
        return self.config.paths.titles_for(self.channel)

    def translation_config(self) -> TranslationConfig:
        return TranslationConfig.from_app_config(channel=self.channel, app_config=self.config)

    def formatting_config(self) -> FormattingConfig:
        return FormattingConfig.from_app_config(channel=self.channel, app_config=self.config)

    def title_config(self) -> TitleConfig:
        return TitleConfig.from_app_config(channel=self.channel, app_config=self.config)


@dataclass(slots=True)
class PipelineStep:
    name: str
    handler: Callable[[PipelineContext], None]
    depends_on: tuple[str, ...] = ()


class PipelineRunner:
    """Executes registered pipeline steps respecting dependencies."""

    def __init__(self, steps: Sequence[PipelineStep]) -> None:
        self._step_map: Dict[str, PipelineStep] = {step.name: step for step in steps}
        self._order = [step.name for step in steps]

    def run(self, context: PipelineContext, *, only: Iterable[str] | None = None) -> None:
        selected = set(only) if only else None
        executed: set[str] = set()
        for name in self._order:
            if selected is not None and name not in selected:
                continue
            step = self._step_map[name]
            if any(dep not in executed for dep in step.depends_on):
                missing = ", ".join(dep for dep in step.depends_on if dep not in executed)
                raise RuntimeError(f"Step '{name}' depends on missing steps: {missing}")
            LOGGER.info("Running pipeline step: %s", name)
            step.handler(context)
            executed.add(name)


def _run_fetch(context: PipelineContext) -> None:
    run_spider(["--spider", context.channel])


def _run_translate(context: PipelineContext) -> None:
    cfg = context.translation_config()
    translator = Translator.from_config(
        config=cfg,
        overwrite=context.overwrite,
        relative_to=context.default_raw_root,
        api_key=context.api_key,
    )
    context.translated_files = translator.translate_glob(cfg.input_glob)


def _run_format(context: PipelineContext) -> None:
    cfg = context.formatting_config()
    formatter = Formatter.from_config(
        config=cfg,
        overwrite=context.overwrite,
        relative_to=context.translated_root,
        api_key=context.api_key,
    )
    if context.translated_files:
        context.formatted_files = formatter.format_many(context.translated_files)
    else:
        context.formatted_files = formatter.format_glob(cfg.input_glob)


def _run_title(context: PipelineContext) -> None:
    cfg = context.title_config()
    generator = TitleGenerator.from_config(
        config=cfg,
        overwrite=context.overwrite,
        relative_to=context.translated_root,
        api_key=context.api_key,
    )
    sources = context.translated_files or sorted(Path().glob(cfg.input_glob))
    context.title_files = generator.generate_many(sources)


def _run_publish(context: PipelineContext) -> None:
    translated_root = context.translated_root
    article_path = _select_translated_article(translated_root, context.translated_files)

    raw_root = context.default_raw_root
    images = _collect_images(raw_root)

    title_text = _load_title(article_path, context.title_files)

    metadata = ArticleMetadata(
        channel=context.channel,
        article_path=article_path,
        title=title_text,
    )

    api_client = WeChatApiClient()
    token_path = context.config.paths.state_dir / "wechat_token.json"
    token_path.parent.mkdir(parents=True, exist_ok=True)
    credential_store = WeChatCredentialStore(token_cache_path=token_path, api_client=api_client)
    media_uploader = WeChatMediaUploader(credential_store)
    draft_client = WeChatDraftClient(credential_store)
    workflow = WeChatArticleWorkflow(media_uploader, draft_client)

    bundle = ContentBundle(channel=context.channel, article_path=article_path, images=images)

    try:
        result = workflow.publish(bundle, metadata, dry_run=context.dry_run)
    except (WeChatApiError, RuntimeError, FileNotFoundError) as exc:
        raise RuntimeError(f"Publish step failed: {exc}") from exc

    LOGGER.info("WeChat draft created media_id=%s", result.media_id)


def _select_translated_article(root: Path, candidates: list[Path]) -> Path:
    if candidates:
        return max(candidates, key=lambda p: p.stat().st_mtime)
    pool = sorted(root.glob("*.translated.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not pool:
        raise FileNotFoundError(f"目录 {root} 中未发现翻译文件")
    return pool[0]


def _collect_images(raw_root: Path) -> list[Path]:
    image_dir = raw_root / "images"
    if not image_dir.is_dir():
        raise FileNotFoundError(f"未找到图片目录: {image_dir}")
    images = sorted(p for p in image_dir.iterdir() if p.is_file() and p.name.lower().startswith("image_"))
    if not images:
        raise FileNotFoundError(f"目录 {image_dir} 中未找到任何 image_* 文件")
    return images


def _load_title(article_path: Path, generated: list[Path]) -> str:
    expected_name = article_path.name.replace(".translated.txt", ".title.txt")
    title_path = article_path.with_name(expected_name)
    if title_path.exists():
        return title_path.read_text(encoding="utf-8").strip()
    for candidate in generated:
        if candidate.name == expected_name:
            return candidate.read_text(encoding="utf-8").strip()
    return article_path.stem.replace("_", " ").replace("-", " ").strip().title()


DEFAULT_STEPS = [
    PipelineStep("fetch", _run_fetch),
    PipelineStep("translate", _run_translate, depends_on=("fetch",)),
    PipelineStep("format", _run_format, depends_on=("translate",)),
    PipelineStep("title", _run_title, depends_on=("translate",)),
    PipelineStep("publish", _run_publish, depends_on=("format", "title")),
]


def build_default_runner(config: AppConfig | None = None, *, channel: str | None = None, **options: object) -> tuple[PipelineRunner, PipelineContext]:
    app_config = config or load_config()
    if not channel:
        channel = app_config.pipeline.default_channel or app_config.default_spider
    ctx = PipelineContext(
        config=app_config,
        channel=channel,
        api_key=options.get("api_key"),
        overwrite=bool(options.get("overwrite", False)),
        dry_run=bool(options.get("dry_run", False)),
    )
    return PipelineRunner(DEFAULT_STEPS), ctx


__all__ = [
    "PipelineContext",
    "PipelineRunner",
    "PipelineStep",
    "DEFAULT_STEPS",
    "build_default_runner",
]
