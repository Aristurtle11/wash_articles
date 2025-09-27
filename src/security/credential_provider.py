"""Interfaces and basic implementations for secret resolution."""

from __future__ import annotations

from abc import ABC, abstractmethod
from configparser import ConfigParser
from pathlib import Path
from typing import Iterable, Mapping


class SecretNotFoundError(KeyError):
    """Raised when a secret cannot be resolved."""


class SecretProvider(ABC):
    """Abstract secret lookup contract."""

    @abstractmethod
    def get_secret(self, key: str) -> str:
        """Return the secret associated with ``key``."""


class EnvSecretProvider(SecretProvider):
    """Reads secrets from process environment variables."""

    def __init__(self, prefix: str = "") -> None:
        from os import environ

        self._env = environ
        self._prefix = prefix

    def get_secret(self, key: str) -> str:
        compound = f"{self._prefix}{key}" if self._prefix else key
        try:
            return self._env[compound.upper().replace(".", "_")]
        except KeyError as exc:
            raise SecretNotFoundError(compound) from exc


class FileSecretProvider(SecretProvider):
    """Loads secrets from INI-style files."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._parser = ConfigParser()
        if path.exists():
            self._parser.read(path, encoding="utf-8")

    def get_secret(self, key: str) -> str:
        section, _, option = key.partition(".")
        if not section or not option:
            raise SecretNotFoundError(key)
        if self._parser.has_option(section, option):
            value = self._parser.get(section, option)
            if value:
                return value
        raise SecretNotFoundError(key)


class MappingSecretProvider(SecretProvider):
    """Wraps a simple dictionary for testing."""

    def __init__(self, mapping: Mapping[str, str]) -> None:
        self._mapping = mapping

    def get_secret(self, key: str) -> str:
        try:
            return self._mapping[key]
        except KeyError as exc:
            raise SecretNotFoundError(key) from exc


class ChainedSecretProvider(SecretProvider):
    """Tries multiple providers until one returns a secret."""

    def __init__(self, providers: Iterable[SecretProvider]) -> None:
        self._providers = tuple(providers)

    def get_secret(self, key: str) -> str:
        for provider in self._providers:
            try:
                return provider.get_secret(key)
            except SecretNotFoundError:
                continue
        raise SecretNotFoundError(key)


__all__ = [
    "ChainedSecretProvider",
    "EnvSecretProvider",
    "FileSecretProvider",
    "MappingSecretProvider",
    "SecretNotFoundError",
    "SecretProvider",
]
