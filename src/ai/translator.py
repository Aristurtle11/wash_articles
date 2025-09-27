"""High-level translation helper built on Gemini."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from ..settings import load_config
from ..utils.logging import get_logger
from .gemini_client import GeminiClient, GeminiError

LOGGER = get_logger(__name__)


@dataclass(slots=True)
class TranslationConfig:
    model: str
    prompt_path: Path
    output_dir: Path
    input_glob: str
    target_language: str
    timeout: float

    @classmethod
    def from_app_config(cls) -> "TranslationConfig":
        config = load_config()
        ai = config.ai
        return cls(
            model=ai.model,
            prompt_path=ai.prompt_path,
            output_dir=ai.output_dir,
            input_glob=ai.input_glob,
            target_language=ai.target_language,
            timeout=ai.timeout,
        )


class Translator:
    def __init__(
        self,
        client: GeminiClient,
        *,
        prompt: str,
        language: str,
        output_dir: Path,
        overwrite: bool = False,
        relative_to: Path | None = None,
    ) -> None:
        self._client = client
        self._prompt_template = prompt
        self._language = language
        self._output_dir = output_dir
        self._overwrite = overwrite
        self._relative_to = relative_to.resolve() if relative_to else None

    @classmethod
    def from_config(
        cls,
        *,
        api_key: str | None = None,
        config: TranslationConfig | None = None,
        overwrite: bool = False,
        relative_to: Path | None = None,
    ) -> "Translator":
        cfg = config or TranslationConfig.from_app_config()
        prompt_text = Path(cfg.prompt_path)
        prompt = prompt_text.read_text(encoding="utf-8")
        client = GeminiClient(api_key=api_key, model=cfg.model, timeout=cfg.timeout)
        output_dir = Path(cfg.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        LOGGER.info(
            "Initialized Translator model=%s prompt=%s output_dir=%s language=%s",
            cfg.model,
            prompt_text,
            output_dir,
            cfg.target_language,
        )
        return cls(
            client,
            prompt=prompt,
            language=cfg.target_language,
            output_dir=output_dir,
            overwrite=overwrite,
            relative_to=relative_to,
        )

    def translate_file(self, input_path: Path) -> Path:
        if self._relative_to and input_path.resolve().is_relative_to(self._relative_to):
            relative = input_path.resolve().relative_to(self._relative_to)
        else:
            relative = input_path.name
        if isinstance(relative, Path):
            relative = relative
        else:
            relative = Path(relative)
        output_path = self._output_dir / relative.with_suffix(".translated.txt")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._overwrite and output_path.exists():
            LOGGER.info("Skipping existing translation %s", output_path)
            return output_path

        text = input_path.read_text(encoding="utf-8")
        request_text = self._prompt_template.format(text=text, language=self._language)
        try:
            translation = self._client.generate(
                prompt=f"You are a professional translator. Target language: {self._language}.",
                user_text=request_text,
            )
        except GeminiError:
            raise
        output_path.write_text(translation, encoding="utf-8")
        LOGGER.info("Wrote translation to %s", output_path)
        return output_path

    def translate_many(self, paths: Sequence[Path]) -> list[Path]:
        results: list[Path] = []
        for path in paths:
            try:
                results.append(self.translate_file(path))
            except GeminiError as exc:
                LOGGER.error("Translation failed for %s: %s", path, exc)
        return results

    def translate_glob(self, pattern: str) -> list[Path]:
        files = sorted(Path().glob(pattern))
        if not files:
            LOGGER.warning("No files matched pattern %s", pattern)
            return []
        return self.translate_many(files)
