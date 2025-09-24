"""Utility script to refresh cookies for a given URL."""

from __future__ import annotations

import argparse
import json
from typing import Sequence

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.http_client import HttpClient, HttpRequest
from src.settings import load_config, load_default_headers
from src.utils.logging import configure_logging, get_logger

LOGGER = get_logger(__name__)


def fetch(url: str, *, config_path: str | None = None) -> None:
    config = load_config(config_path)
    headers = load_default_headers()
    client = HttpClient(
        http_settings=config.http,
        cookie_path=config.paths.cookie_jar,
        default_headers=headers,
    )
    LOGGER.info("Fetching cookies from %s", url)
    response = client.fetch(HttpRequest(url=url))
    snippet = response.text[:200]
    LOGGER.info("Response status %s", response.status)
    print(json.dumps(snippet, ensure_ascii=False))


def main(argv: Sequence[str] | None = None) -> None:
    configure_logging()
    parser = argparse.ArgumentParser(description="Fetch cookies and update default headers")
    parser.add_argument("url", help="URL to request")
    parser.add_argument("--config", help="Alternative config path")
    args = parser.parse_args(argv)
    fetch(args.url, config_path=args.config)


if __name__ == "__main__":
    main()
