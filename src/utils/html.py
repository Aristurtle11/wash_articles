"""Helpers for parsing HTML content."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup


def load_local_html(path: Path, *, parser: str = "html.parser") -> BeautifulSoup:
    with path.open("r", encoding="utf-8") as fp:
        return BeautifulSoup(fp.read(), parser)
