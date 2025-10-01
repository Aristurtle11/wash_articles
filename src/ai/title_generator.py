"""AI helper for crafting Chinese WeChat headlines."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from google import genai

from .base_node import BaseAIConfig, BaseAIGenerator
from ..settings import load_config
from ..utils.logging import get_logger

LOGGER = get_logger(__name__)


@dataclass(slots=True)
class TitleConfig(BaseAIConfig):
    """Configuration values for title generation."""

    @classmethod
    def from_app_config(cls, *, channel: str | None = None) -> "TitleConfig":
        app_config = load_config()
        stage = app_config.title_for(channel) if channel is not None else app_config.title

        prompt_source = stage.prompt_path or stage.prompt_fallback or (
            app_config.paths.data_dir / "prompts" / "title_prompt.txt"
        )
        output_source = stage.output_dir or stage.output_dir_fallback or app_config.paths.titles_for(channel)
        input_glob = stage.input_glob or str(app_config.paths.translated_for(channel) / "**/*.translated.txt")
        timeout = stage.timeout or 30

        return cls(
            model=stage.model or "",
            prompt_path=Path(prompt_source),
            output_dir=Path(output_source),
            input_glob=input_glob,
            timeout=timeout,
            thinking_budget=stage.thinking_budget,
        )


class TitleGenerator(BaseAIGenerator):
    """Produce attention-grabbing yet faithful Chinese headlines."""

    output_suffix = ".title.txt"

    def __init__(
        self,
        client: genai.Client,
        *,
        prompt: str,
        output_dir: Path,
        overwrite: bool,
        relative_to: Path | None,
        model: str,
        thinking_budget: int | None,
        timeout: float,
    ) -> None:
        super().__init__(
            client,
            prompt=prompt,
            output_dir=output_dir,
            overwrite=overwrite,
            relative_to=relative_to,
            model=model,
            thinking_budget=thinking_budget,
            timeout=timeout,
            logger=LOGGER,
        )

    @classmethod
    def from_config(
        cls,
        *,
        config: TitleConfig | None = None,
        overwrite: bool = False,
        relative_to: Path | None = None,
        api_key: str | None = None,
    ) -> "TitleGenerator":
        cfg = config or TitleConfig.from_app_config()
        prompt = cfg.prompt_path.read_text(encoding="utf-8")

        client = BaseAIGenerator.create_client(api_key=api_key)
        cfg.output_dir.mkdir(parents=True, exist_ok=True)

        LOGGER.info(
            "Initialized TitleGenerator model=%s prompt=%s output_dir=%s",
            cfg.model,
            cfg.prompt_path,
            cfg.output_dir,
        )

        return cls(
            client,
            prompt=prompt,
            output_dir=cfg.output_dir,
            overwrite=overwrite,
            relative_to=relative_to,
            model=cfg.model,
            thinking_budget=cfg.thinking_budget,
            timeout=cfg.timeout,
        )

    def generate_title_file(self, input_path: Path) -> Path:
        return self.process_file(input_path)

    def generate_many(self, paths: Sequence[Path]) -> list[Path]:
        return self.process_many(paths)

    def generate_glob(self, pattern: str) -> list[Path]:
        files = sorted(Path().glob(pattern))
        if not files:
            LOGGER.warning("No files matched pattern %s", pattern)
            return []
        return self.generate_many(files)

    def render_prompt(self, source_text: str) -> str:
        return self._prompt_template.format(text=source_text)

    def postprocess(self, raw_text: str) -> str:
        cleaned = self._clean_title(raw_text)
        if not cleaned:
            raise RuntimeError("AI 返回标题为空，无法继续")
        return cleaned + "\n"

    @staticmethod
    def _clean_title(raw: str) -> str:
        """Normalize title output by stripping control characters and adornments."""
        text = raw.strip()
        if not text:
            return ""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return ""
        title = lines[0]
        for ch in ('`', '"', "'", "\u300a", "\u300b"):
            title = title.strip(ch)
        return title.strip()
