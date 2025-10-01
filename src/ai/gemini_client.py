"""Minimal Gemini API client built on urllib."""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping

LOGGER = logging.getLogger(__name__)


class GeminiError(RuntimeError):
    """Raised when the Gemini API returns an error response."""


@dataclass(slots=True)
class GenerationConfig:
    temperature: float = 0.2
    top_k: int | None = None
    top_p: float | None = None
    max_output_tokens: int | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"temperature": self.temperature}
        if self.top_k is not None:
            payload["topK"] = self.top_k
        if self.top_p is not None:
            payload["topP"] = self.top_p
        if self.max_output_tokens is not None:
            payload["maxOutputTokens"] = self.max_output_tokens
        return payload


class GeminiClient:
    """Tiny wrapper around the Gemini REST API."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "gemini-1.5-flash",
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        timeout: float = 30.0,
        max_retries: int = 3,
        backoff_seconds: float = 2.0,
        generation_config: GenerationConfig | None = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self._api_key:
            raise GeminiError(
                "Gemini API key not provided. Set GEMINI_API_KEY or pass api_key explicitly."
            )
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._generation_config = generation_config or GenerationConfig()
        self._max_retries = max(1, int(max_retries))
        self._backoff = max(0.0, float(backoff_seconds))
        self._opener = urllib.request.build_opener()

    @property
    def model(self) -> str:
        return self._model

    def generate(self, *, prompt: str, user_text: str) -> str:
        """Send a translation request and return the text of the first candidate."""
        url = f"{self._base_url}/models/{urllib.parse.quote(self._model)}:generateContent?key={urllib.parse.quote(self._api_key)}"
        payload: dict[str, Any] = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": prompt},
                        {"text": user_text},
                    ],
                }
            ],
            "generationConfig": self._generation_config.as_dict(),
        }
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url=url,
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": self._api_key,
            },
        )
        for attempt in range(1, self._max_retries + 1):
            start = time.monotonic()
            LOGGER.info(
                "Gemini request start model=%s payload_bytes=%d timeout=%.1fs attempt=%d/%d",
                self._model,
                len(data),
                self._timeout,
                attempt,
                self._max_retries,
            )
            try:
                with self._opener.open(request, timeout=self._timeout) as response:
                    body = response.read()
                    status = getattr(response, "status", 200)
            except TimeoutError as exc:  # pragma: no cover
                duration = time.monotonic() - start
                LOGGER.warning(
                    "Gemini request timed out after %.2fs on attempt %d/%d",
                    duration,
                    attempt,
                    self._max_retries,
                )
                if attempt >= self._max_retries:
                    raise GeminiError(
                        f"Gemini API read timed out after {duration:.2f}s on attempt {attempt}."
                    ) from exc
                time.sleep(self._backoff * attempt)
                continue
            except urllib.error.HTTPError as exc:
                error_body = (
                    exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else ""
                )
                LOGGER.error("Gemini HTTPError %s on attempt %d: %s", exc.code, attempt, error_body)
                raise GeminiError(f"Gemini API error {exc.code}: {error_body}") from exc
            except urllib.error.URLError as exc:
                duration = time.monotonic() - start
                LOGGER.warning(
                    "Gemini URLError after %.2fs on attempt %d/%d: %s",
                    duration,
                    attempt,
                    self._max_retries,
                    exc,
                )
                if attempt >= self._max_retries:
                    raise GeminiError(f"Gemini API connection error: {exc}") from exc
                time.sleep(self._backoff * attempt)
                continue

            if status >= 400:
                raise GeminiError(f"Gemini API returned status {status}")

            try:
                payload = json.loads(body)
            except json.JSONDecodeError as exc:
                raise GeminiError(
                    f"Failed to decode Gemini response: {exc}\nRaw: {body[:200]!r}"
                ) from exc

            text = self._extract_text(payload)
            if text is None:
                raise GeminiError(
                    f"Gemini response missing candidates: {json.dumps(payload)[:500]}"
                )
            duration = time.monotonic() - start
            LOGGER.info("Gemini request succeeded in %.2fs on attempt %d", duration, attempt)
            return text

        raise GeminiError("Gemini request failed after retries")

    def _extract_text(self, payload: Mapping[str, Any]) -> str | None:
        candidates = payload.get("candidates")
        if not candidates:
            return None
        for candidate in candidates:
            content = candidate.get("content") or {}
            parts = content.get("parts") or []
            for part in parts:
                text = part.get("text")
                if text:
                    return text
        return None
