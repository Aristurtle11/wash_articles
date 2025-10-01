"""Filesystem helpers."""

from __future__ import annotations

from pathlib import Path


def ensure_parent(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def read_text(path: Path, *, encoding: str = "utf-8") -> str:
    with path.open("r", encoding=encoding) as fp:
        return fp.read()


def write_text(path: Path, data: str, *, encoding: str = "utf-8") -> None:
    ensure_parent(path)
    with path.open("w", encoding=encoding) as fp:
        fp.write(data)
