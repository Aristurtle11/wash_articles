"""Factory helpers for platform publishers."""

from __future__ import annotations

from typing import Callable, Mapping

from src.platforms.base import ContentPublisher, PlatformFactory


class DictPlatformFactory(PlatformFactory):
    """Simple registry-backed factory."""

    def __init__(self, builders: Mapping[str, Callable[[], ContentPublisher]]) -> None:
        self._builders = {key.lower(): value for key, value in builders.items()}

    def create(self, platform: str) -> ContentPublisher:
        key = platform.lower()
        try:
            builder = self._builders[key]
        except KeyError as exc:
            raise ValueError(f"Unsupported platform: {platform}") from exc
        return builder()
