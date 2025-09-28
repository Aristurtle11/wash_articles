"""AI-powered article formatting helpers."""

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
class FormattingConfig:
    """Configuration values for the formatting workflow."""

    model: str
    prompt_path: Path
    output_dir: Path
    input_glob: str
    timeout: float
    thinking_budget: int | None = None

    @classmethod
    def from_app_config(cls) -> "FormattingConfig":
        config = load_config()
        fmt = config.formatting
        return cls(
            model=fmt.model,
            prompt_path=fmt.prompt_path,
            output_dir=fmt.output_dir,
            input_glob=fmt.input_glob,
            timeout=fmt.timeout,
            thinking_budget=fmt.thinking_budget,
        )


class Formatter:
    """Turns translated plain text into lightly styled HTML."""

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
        self._client = client
        self._prompt_template = prompt
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
        config: FormattingConfig | None = None,
        overwrite: bool = False,
        relative_to: Path | None = None,
        api_key: str | None = None,
    ) -> "Formatter":
        cfg = config or FormattingConfig.from_app_config()
        prompt_path = Path(cfg.prompt_path)
        prompt = prompt_path.read_text(encoding="utf-8")

        resolved_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not resolved_key:
            raise RuntimeError(
                "Gemini API key not found. Set GEMINI_API_KEY or pass --api-key."
            )

        client = genai.Client(api_key=resolved_key)

        output_dir = Path(cfg.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        LOGGER.info(
            "Initialized Formatter model=%s prompt=%s output_dir=%s",
            cfg.model,
            prompt_path,
            output_dir,
        )

        return cls(
            client,
            prompt=prompt,
            output_dir=output_dir,
            overwrite=overwrite,
            relative_to=relative_to,
            model=cfg.model,
            thinking_budget=cfg.thinking_budget,
            timeout=cfg.timeout,
        )

    def format_file(self, input_path: Path) -> Path:
        """Format a translated text file into HTML and return output path."""

        resolved_input = input_path.resolve()
        if self._relative_to and resolved_input.is_relative_to(self._relative_to):
            relative_path = resolved_input.relative_to(self._relative_to)
        else:
            relative_path = resolved_input.name
        relative_path = relative_path if isinstance(relative_path, Path) else Path(relative_path)

        output_path = self._output_dir / relative_path.with_suffix(".formatted.html")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if not self._overwrite and output_path.exists():
            LOGGER.info("Skipping existing formatted file %s", output_path)
            return output_path

        source_text = resolved_input.read_text(encoding="utf-8")
        prompt_text = self._prompt_template.format(text=source_text)

        request_kwargs: dict[str, object] = {
            "model": self._model,
            "contents": prompt_text,
        }

        if self._thinking_budget and self._thinking_budget > 0:
            request_kwargs["config"] = types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=self._thinking_budget)
            )
            LOGGER.debug(
                "Gemini formatting thinking mode enabled budget=%s for %s",
                self._thinking_budget,
                resolved_input,
            )

        LOGGER.info(
            "Sending Gemini formatting request model=%s input=%s chars=%s",
            self._model,
            resolved_input,
            len(prompt_text),
        )

        try:
            response = self._client.models.generate_content(**request_kwargs)
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(f"Gemini API call failed: {exc}") from exc

        formatted = response.text or ""
        output_path.write_text(formatted, encoding="utf-8")
        LOGGER.info("Wrote formatted HTML to %s", output_path)
        return output_path

    def format_many(self, paths: Sequence[Path]) -> list[Path]:
        results: list[Path] = []
        for path in paths:
            try:
                results.append(self.format_file(path))
            except Exception as exc:  # pragma: no cover
                LOGGER.error("Formatting failed for %s: %s", path, exc)
        return results

    def format_glob(self, pattern: str) -> list[Path]:
        files = sorted(Path().glob(pattern))
        if not files:
            LOGGER.warning("No files matched pattern %s", pattern)
            return []
        return self.format_many(files)
