"""High-level translation helpers powered by google-genai SDK."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from google import genai
from google.genai import types

from ..settings import load_config
from ..utils.logging import get_logger

LOGGER = get_logger(__name__)


@dataclass(slots=True)
class TranslationConfig:
    """Configuration values for the translation workflow."""

    model: str
    prompt_path: Path
    output_dir: Path
    input_glob: str
    target_language: str
    timeout: float
    thinking_budget: int | None = None

    @classmethod
    def from_app_config(cls, *, channel: str | None = None) -> "TranslationConfig":
        app_config = load_config()
        stage = app_config.ai_for(channel) if channel is not None else app_config.ai

        prompt_source = stage.prompt_path or stage.prompt_fallback or (app_config.paths.data_dir / "prompts" / "translation_prompt.txt")
        output_source = stage.output_dir or stage.output_dir_fallback or app_config.paths.translated_for(channel)
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



class Translator:
    """Orchestrates prompt construction and Gemini API invocations."""

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
        self._client = client
        self._prompt_template = prompt
        self._language = language
        self._output_dir = output_dir
        self._overwrite = overwrite
        self._relative_to = relative_to.resolve() if relative_to else None
        self._model = model
        self._thinking_budget = thinking_budget
        self._timeout = timeout

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
        prompt_path = Path(cfg.prompt_path)
        prompt = prompt_path.read_text(encoding="utf-8")

        resolved_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not resolved_key:
            raise RuntimeError(
                "Gemini API key not found. Set GEMINI_API_KEY or pass --api-key."
            )

        # Initialise google-genai client using the resolved API key.
        client = genai.Client(api_key=resolved_key)

        output_dir = Path(cfg.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        LOGGER.info(
            "Initialized Translator model=%s prompt=%s output_dir=%s language=%s",
            cfg.model,
            prompt_path,
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
            model=cfg.model,
            thinking_budget=cfg.thinking_budget,
            timeout=cfg.timeout,
        )

    def translate_file(self, input_path: Path) -> Path:
        """Translate a single file and return the translated file path."""

        resolved_input = input_path.resolve()
        if self._relative_to and resolved_input.is_relative_to(self._relative_to):
            relative_path = resolved_input.relative_to(self._relative_to)
        else:
            relative_path = resolved_input.name
        relative_path = relative_path if isinstance(relative_path, Path) else Path(relative_path)

        output_path = self._output_dir / relative_path.with_suffix(".translated.txt")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if not self._overwrite and output_path.exists():
            LOGGER.info("Skipping existing translation %s", output_path)
            return output_path

        source_text = resolved_input.read_text(encoding="utf-8")
        prompt_text = self._prompt_template.format(text=source_text, language=self._language)

        request_kwargs: dict[str, object] = {
            "model": self._model,
            "contents": prompt_text,
        }

        if self._thinking_budget and self._thinking_budget > 0:
            request_kwargs["config"] = types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=self._thinking_budget)
            )
            LOGGER.debug(
                "Gemini thinking mode enabled budget=%s for %s",
                self._thinking_budget,
                resolved_input,
            )
        elif self._thinking_budget is not None and self._thinking_budget <= 0:
            LOGGER.debug(
                "Skipping Gemini thinking mode because budget=%s for %s",
                self._thinking_budget,
                resolved_input,
            )

        LOGGER.info(
            "Sending Gemini translation request model=%s input=%s chars=%s",
            self._model,
            resolved_input,
            len(prompt_text),
        )

        try:
            response = self._client.models.generate_content(**request_kwargs)
        except Exception as exc:  # pragma: no cover - network/SDK errors only at runtime
            raise RuntimeError(f"Gemini API call failed: {exc}") from exc

        translation = response.text or ""
        output_path.write_text(translation, encoding="utf-8")
        LOGGER.info("Wrote translation to %s", output_path)
        return output_path

    def translate_many(self, paths: Sequence[Path]) -> list[Path]:
        results: list[Path] = []
        for path in paths:
            try:
                results.append(self.translate_file(path))
            except Exception as exc:  # pragma: no cover
                LOGGER.error("Translation failed for %s: %s", path, exc)
        return results

    def translate_glob(self, pattern: str) -> list[Path]:
        files = sorted(Path().glob(pattern))
        if not files:
            LOGGER.warning("No files matched pattern %s", pattern)
            return []
        return self.translate_many(files)
