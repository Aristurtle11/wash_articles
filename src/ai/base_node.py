"""Shared helpers for Gemini-powered generators."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from google import genai
from google.genai import types

from ..utils.logging import get_logger

LOGGER = get_logger(__name__)


@dataclass(slots=True)
class BaseAIConfig:
    """Configuration shared by AI generators."""

    model: str
    prompt_path: Path
    output_dir: Path
    input_glob: str
    timeout: float
    thinking_budget: int | None = None


class BaseAIGenerator:
    """Reusable scaffold for translating, formatting, and titling tasks."""

    output_suffix: str = ""

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
        logger: logging.Logger | None = None,
    ) -> None:
        self._client = client
        self._prompt_template = prompt
        self._output_dir = output_dir
        self._overwrite = overwrite
        self._relative_to = relative_to.resolve() if relative_to else None
        self._model = model
        self._thinking_budget = thinking_budget
        self._timeout = timeout
        self._logger = logger or LOGGER

    @staticmethod
    def load_prompt_text(prompt_path: Path) -> str:
        """Load a prompt from a file or concatenate all .txt files in a directory."""
        if prompt_path.is_dir():
            parts: list[str] = []
            for file in sorted(prompt_path.glob("*.txt")):
                content = file.read_text(encoding="utf-8").strip()
                if content:
                    parts.append(content)
            if not parts:
                raise RuntimeError(f"No prompt files found in {prompt_path}")
            return "\n\n".join(parts)
        return prompt_path.read_text(encoding="utf-8")


    @staticmethod
    def create_client(api_key: str | None = None) -> genai.Client:
        resolved_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not resolved_key:
            raise RuntimeError(
                "Gemini API key not found. Set GEMINI_API_KEY or pass --api-key."
            )
        return genai.Client(api_key=resolved_key)

    def _relative_path(self, input_path: Path) -> Path:
        resolved = input_path.resolve()
        if self._relative_to and resolved.is_relative_to(self._relative_to):
            relative_path = resolved.relative_to(self._relative_to)
        else:
            relative_path = resolved.name
        return relative_path if isinstance(relative_path, Path) else Path(relative_path)

    def _make_request(self, prompt_text: str) -> str:
        request_kwargs: dict[str, object] = {
            "model": self._model,
            "contents": prompt_text,
        }
        if self._thinking_budget and self._thinking_budget > 0:
            request_kwargs["config"] = types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=self._thinking_budget)
            )
            self._logger.debug("Thinking mode enabled budget=%s", self._thinking_budget)
        response = self._client.models.generate_content(**request_kwargs)
        return response.text or ""

    def process_file(self, input_path: Path) -> Path:
        relative_path = self._relative_path(input_path)
        output_path = self._output_dir / relative_path.with_suffix(self.output_suffix)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if not self._overwrite and output_path.exists():
            self._logger.info("Skipping existing output %s", output_path)
            return output_path

        source_text = input_path.read_text(encoding="utf-8")
        prompt_text = self.render_prompt(source_text)
        response_text = self._make_request(prompt_text)
        final_text = self.postprocess(response_text)
        output_path.write_text(final_text, encoding="utf-8")
        self._logger.info("Wrote output to %s", output_path)
        return output_path

    def process_many(self, paths: Sequence[Path]) -> list[Path]:
        results: list[Path] = []
        for path in paths:
            try:
                results.append(self.process_file(path))
            except Exception as exc:  # pragma: no cover - runtime logging aid
                self._logger.error("Processing failed for %s: %s", path, exc)
        return results

    def render_prompt(self, source_text: str) -> str:  # pragma: no cover - abstract hook
        raise NotImplementedError

    def postprocess(self, raw_text: str) -> str:
        return raw_text
