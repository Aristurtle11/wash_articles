"""Helpers for loading configuration and static settings."""

from __future__ import annotations

import json
import os
from configparser import ConfigParser
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_NAME = "config.ini"
CONFIG_ENV_VAR = "WASH_CONFIG"
DEFAULT_HEADERS_PATH = Path(__file__).with_name("default_headers.json")
DEFAULT_HEADERS_TEMPLATE_PATH = Path(__file__).with_name("default_headers.template.json")


@dataclass(slots=True)
class HttpSettings:
    timeout: float
    min_delay: float
    max_delay: float
    max_attempts: int
    backoff_factor: float


@dataclass(slots=True)
class PathSettings:
    data_dir: Path
    raw_dir: Path
    processed_dir: Path
    log_dir: Path
    state_dir: Path
    cookie_jar: Path


@dataclass(slots=True)
class AppConfig:
    default_spider: str
    http: HttpSettings
    paths: PathSettings
    spiders: dict[str, dict[str, str]]


def _to_path(value: str | None, *, fallback: Path) -> Path:
    if not value:
        return fallback
    candidate = Path(value)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _load_parser(config_path: Path) -> ConfigParser:
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    parser = ConfigParser()
    parser.read(config_path)
    return parser


def _config_path(explicit: str | os.PathLike[str] | None = None) -> Path:
    candidate: Path
    if explicit:
        candidate = Path(explicit)
    else:
        env_value = os.environ.get(CONFIG_ENV_VAR)
        candidate = Path(env_value) if env_value else PROJECT_ROOT / DEFAULT_CONFIG_NAME
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def load_config(config_path: str | os.PathLike[str] | None = None) -> AppConfig:
    path = _config_path(config_path)
    parser = _load_parser(path)

    app_section = parser["app"] if parser.has_section("app") else {}
    paths_section = parser["paths"] if parser.has_section("paths") else {}
    http_section = parser["http"] if parser.has_section("http") else {}

    data_dir = _to_path(paths_section.get("data_dir"), fallback=PROJECT_ROOT / "data")
    raw_dir = _to_path(paths_section.get("raw_dir"), fallback=data_dir / "raw")
    processed_dir = _to_path(paths_section.get("processed_dir"), fallback=data_dir / "processed")
    log_dir = _to_path(paths_section.get("log_dir"), fallback=data_dir / "logs")
    state_dir = _to_path(paths_section.get("state_dir"), fallback=data_dir / "state")
    cookie_path = _to_path(paths_section.get("cookie_jar"), fallback=state_dir / "cookies.txt")

    for directory in (data_dir, raw_dir, processed_dir, log_dir, state_dir, cookie_path.parent):
        directory.mkdir(parents=True, exist_ok=True)

    http_settings = HttpSettings(
        timeout=float(http_section.get("timeout", 10)),
        min_delay=float(http_section.get("min_delay", 0)),
        max_delay=float(http_section.get("max_delay", 0)),
        max_attempts=int(http_section.get("max_attempts", 3)),
        backoff_factor=float(http_section.get("backoff_factor", 1.5)),
    )

    spiders: dict[str, dict[str, str]] = {}
    for section in parser.sections():
        if section.lower().startswith("spider:"):
            spider_name = section.split(":", 1)[1].strip()
            spiders[spider_name] = {k: v for k, v in parser[section].items()}

    config = AppConfig(
        default_spider=app_section.get("default_spider", "example"),
        http=http_settings,
        paths=PathSettings(
            data_dir=data_dir,
            raw_dir=raw_dir,
            processed_dir=processed_dir,
            log_dir=log_dir,
            state_dir=state_dir,
            cookie_jar=cookie_path,
        ),
        spiders=spiders,
    )
    return config


def load_default_headers() -> dict[str, str]:
    path = DEFAULT_HEADERS_PATH
    if not path.exists():
        template = DEFAULT_HEADERS_TEMPLATE_PATH
        if template.exists():
            data = _load_headers(template)
            save_default_headers(data)
            return data
        return {}
    return _load_headers(path)


def _load_headers(path: Path) -> dict[str, str]:
    with path.open("r", encoding="utf-8") as fp:
        data = json.load(fp)
    return {str(key): str(value) for key, value in data.items()}


def save_default_headers(headers: dict[str, str]) -> None:
    DEFAULT_HEADERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with DEFAULT_HEADERS_PATH.open("w", encoding="utf-8") as fp:
        json.dump(headers, fp, ensure_ascii=True, indent=2, sort_keys=True)


def project_path(*parts: Any) -> Path:
    return PROJECT_ROOT.joinpath(*parts)
