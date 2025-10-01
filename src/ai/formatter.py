"""AI-powered article formatting helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from google import genai

from .base_node import BaseAIConfig, BaseAIGenerator
from ..settings import load_config
from ..utils.logging import get_logger

LOGGER = get_logger(__name__)


@dataclass(slots=True)
class FormattingConfig(BaseAIConfig):
    """Configuration values for the formatting workflow."""

    @classmethod
    def from_app_config(cls, *, channel: str | None = None) -> "FormattingConfig":
        app_config = load_config()
        stage = app_config.formatting_for(channel) if channel is not None else app_config.formatting

        prompt_source = stage.prompt_path or stage.prompt_fallback
        if prompt_source is None:
            prompt_source = Path(__file__).resolve().parents[2] / "prompts" / "format"
        output_source = stage.output_dir or stage.output_dir_fallback or app_config.paths.formatted_for(channel)
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


class Formatter(BaseAIGenerator):
    """Turns translated plain text into lightly styled HTML."""

    output_suffix = ".formatted.html"

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
        config: FormattingConfig | None = None,
        overwrite: bool = False,
        relative_to: Path | None = None,
        api_key: str | None = None,
    ) -> "Formatter":
        cfg = config or FormattingConfig.from_app_config()
        prompt = BaseAIGenerator.load_prompt_text(cfg.prompt_path)

        client = BaseAIGenerator.create_client(api_key=api_key)
        cfg.output_dir.mkdir(parents=True, exist_ok=True)

        LOGGER.info(
            "Initialized Formatter model=%s prompt=%s output_dir=%s",
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

    def format_file(self, input_path: Path) -> Path:
        return self.process_file(input_path)

    def format_many(self, paths: Sequence[Path]) -> list[Path]:
        return self.process_many(paths)

    def format_glob(self, pattern: str) -> list[Path]:
        files = sorted(Path().glob(pattern))
        if not files:
            LOGGER.warning("No files matched pattern %s", pattern)
            return []
        return self.format_many(files)

    def render_prompt(self, source_text: str) -> str:
        return self._prompt_template.format(text=source_text)

    def postprocess(self, raw_text: str) -> str:
        return self._strip_block_leading_whitespace(raw_text)

    @staticmethod
    def _strip_block_leading_whitespace(html: str) -> str:
        """Remove indentation that would surface as visible spaces in WeChat."""
        if not html:
            return html
        pattern = re.compile(r"(<(?:p|h[1-6]|blockquote|li|figure)[^>]*>)\s+", re.IGNORECASE)
        return pattern.sub(r"\1", html)
