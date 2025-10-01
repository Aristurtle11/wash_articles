"""High-level translation helpers powered by google-genai SDK."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from google import genai

from .base_node import BaseAIConfig, BaseAIGenerator
from ..settings import AppConfig, load_config
from ..utils.logging import get_logger

LOGGER = get_logger(__name__)


@dataclass(slots=True)
class TranslationConfig(BaseAIConfig):
    """Configuration values for the translation workflow."""

    target_language: str

    @classmethod
    def from_app_config(
        cls,
        *,
        channel: str | None = None,
        app_config: AppConfig | None = None,
    ) -> "TranslationConfig":
        app_config = load_config() if app_config is None else app_config
        stage = app_config.ai_for(channel) if channel is not None else app_config.ai

        prompt_source = stage.prompt_path or stage.prompt_fallback
        if prompt_source is None:
            prompt_source = Path(__file__).resolve().parents[2] / "prompts" / "translate"
        output_source = (
            stage.output_dir
            or stage.output_dir_fallback
            or app_config.paths.translated_for(channel)
        )
        input_glob = stage.input_glob or str(app_config.paths.raw_for(channel) / "**/*.txt")
        target_language = stage.target_language or "zh-CN"
        timeout = stage.timeout or 30

        return cls(
            model=stage.model or "",
            prompt_path=Path(prompt_source),
            output_dir=Path(output_source),
            input_glob=input_glob,
            target_language=target_language,
            timeout=timeout,
            thinking_budget=stage.thinking_budget,
        )


class Translator(BaseAIGenerator):
    """Orchestrates prompt construction and Gemini API invocations."""

    output_suffix = ".translated.txt"

    def __init__(
        self,
        client: genai.Client,
        *,
        prompt: str,
        language: str,
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
        self._language = language

    @classmethod
    def from_config(
        cls,
        *,
        config: TranslationConfig | None = None,
        overwrite: bool = False,
        relative_to: Path | None = None,
        api_key: str | None = None,
    ) -> "Translator":
        cfg = config or TranslationConfig.from_app_config()
        prompt = BaseAIGenerator.load_prompt_text(cfg.prompt_path)

        client = BaseAIGenerator.create_client(api_key=api_key)
        cfg.output_dir.mkdir(parents=True, exist_ok=True)

        LOGGER.info(
            "Initialized Translator model=%s prompt=%s output_dir=%s language=%s",
            cfg.model,
            cfg.prompt_path,
            cfg.output_dir,
            cfg.target_language,
        )

        return cls(
            client,
            prompt=prompt,
            language=cfg.target_language,
            output_dir=cfg.output_dir,
            overwrite=overwrite,
            relative_to=relative_to,
            model=cfg.model,
            thinking_budget=cfg.thinking_budget,
            timeout=cfg.timeout,
        )

    def translate_file(self, input_path: Path) -> Path:
        """Translate a single file and return the translated file path."""

        return self.process_file(input_path)

    def translate_many(self, paths: Sequence[Path]) -> list[Path]:
        return self.process_many(paths)

    def translate_glob(self, pattern: str) -> list[Path]:
        files = sorted(Path().glob(pattern))
        if not files:
            LOGGER.warning("No files matched pattern %s", pattern)
            return []
        return self.translate_many(files)

    def render_prompt(self, source_text: str) -> str:
        return self._prompt_template.format(text=source_text, language=self._language)
