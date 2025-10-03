"""Helpers for loading configuration and static settings."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

try:  # pragma: no cover - Python 3.11+ includes tomllib
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - fallback for older versions
    import tomli as tomllib  # type: ignore[no-redef]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_NAME = "config.toml"
CONFIG_ENV_VAR = "WASH_CONFIG"
DEFAULT_HEADERS_PATH = Path(__file__).with_name("default_headers.json")
DEFAULT_HEADERS_TEMPLATE_PATH = Path(__file__).with_name("default_headers.template.json")

_STAGE_FALLBACK_PROMPTS = {
    "translate": PROJECT_ROOT / "prompts" / "translate",
    "format": PROJECT_ROOT / "prompts" / "format",
    "title": PROJECT_ROOT / "prompts" / "title",
}

_STAGE_FALLBACK_OUTPUT_DIRS = {
    "translate": PROJECT_ROOT / "data" / "translated",
    "format": PROJECT_ROOT / "data" / "translated",
    "title": PROJECT_ROOT / "data" / "translated",
}

_STAGE_FALLBACK_INPUTS = {
    "translate": "data/{channel}/raw/**/*.txt",
    "format": "data/{channel}/translated/**/*.translated.txt",
    "title": "data/{channel}/translated/**/*.translated.txt",
}


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
    translated_dir: Path
    formatted_dir: Path
    titles_dir: Path
    artifacts_dir: Path
    log_dir: Path
    state_dir: Path
    cookie_jar: Path
    header_jar: Path
    default_channel: str | None = None

    @property
    def processed_dir(self) -> Path:
        return self.artifacts_dir

    def channel_root(self, channel: str | None = None) -> Path:
        name = channel or self.default_channel or "default"
        return self.data_dir / name

    def raw_for(self, channel: str | None = None) -> Path:
        return self.channel_root(channel) / "raw"

    def translated_for(self, channel: str | None = None) -> Path:
        return self.channel_root(channel) / "translated"

    def formatted_for(self, channel: str | None = None) -> Path:
        return self.channel_root(channel) / "formatted"

    def titles_for(self, channel: str | None = None) -> Path:
        return self.channel_root(channel) / "titles"

    def artifacts_for(self, channel: str | None = None) -> Path:
        return self.channel_root(channel) / "artifacts"


@dataclass(slots=True)
class StageSettings:
    """Configuration for a single pipeline stage."""

    name: str
    kind: str
    model: str | None = None
    prompt_path: Path | None = None
    output_dir: Path | None = None
    input_glob: str | None = None
    timeout: float | None = None
    thinking_budget: int | None = None
    target_language: str | None = None
    prompt_template: str | None = None
    output_dir_template: str | None = None
    input_glob_template: str | None = None
    prompt_fallback: Path | None = None
    output_dir_fallback: Path | None = None
    input_glob_fallback: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def for_channel(self, channel: str | None) -> "StageSettings":
        """Return a stage with paths resolved for the given channel."""

        if channel is None:
            return self

        prompt_path = self.prompt_path
        if self.prompt_template and "{channel}" in self.prompt_template:
            fallback = (
                self.prompt_fallback
                or self.prompt_path
                or PROJECT_ROOT / "prompts" / f"{self.name}.txt"
            )
            prompt_path = _resolve_template_to_path(
                self.prompt_template, channel=channel, fallback=fallback
            )

        output_dir = self.output_dir
        if self.output_dir_template and "{channel}" in self.output_dir_template:
            fallback = (
                self.output_dir_fallback or self.output_dir or PROJECT_ROOT / "data" / self.name
            )
            output_dir = _resolve_template_to_path(
                self.output_dir_template, channel=channel, fallback=fallback
            )

        input_glob = self.input_glob
        if self.input_glob_template and "{channel}" in self.input_glob_template:
            fallback = self.input_glob_fallback or self.input_glob
            input_glob = _resolve_template_to_glob(
                self.input_glob_template, channel=channel, fallback=fallback
            )

        return StageSettings(
            name=self.name,
            kind=self.kind,
            model=self.model,
            prompt_path=prompt_path,
            output_dir=output_dir,
            input_glob=input_glob,
            timeout=self.timeout,
            thinking_budget=self.thinking_budget,
            target_language=self.target_language,
            prompt_template=self.prompt_template,
            output_dir_template=self.output_dir_template,
            input_glob_template=self.input_glob_template,
            prompt_fallback=self.prompt_fallback,
            output_dir_fallback=self.output_dir_fallback,
            input_glob_fallback=self.input_glob_fallback,
            extra=self.extra.copy(),
        )

    def as_dict(self) -> dict[str, Any]:
        """Return a serialisable view of the stage."""

        data: dict[str, Any] = {
            "name": self.name,
            "kind": self.kind,
            "model": self.model,
            "prompt_path": str(self.prompt_path) if self.prompt_path else None,
            "output_dir": str(self.output_dir) if self.output_dir else None,
            "input_glob": self.input_glob,
            "timeout": self.timeout,
            "thinking_budget": self.thinking_budget,
            "target_language": self.target_language,
            "prompt_template": self.prompt_template,
            "output_dir_template": self.output_dir_template,
            "input_glob_template": self.input_glob_template,
            "prompt_fallback": str(self.prompt_fallback) if self.prompt_fallback else None,
            "output_dir_fallback": str(self.output_dir_fallback)
            if self.output_dir_fallback
            else None,
            "input_glob_fallback": self.input_glob_fallback,
        }
        data.update(self.extra)
        return data


@dataclass(slots=True)
class PipelineSettings:
    default_channel: str | None
    stages: dict[str, StageSettings]

    def get(self, name: str) -> StageSettings:
        try:
            return self.stages[name]
        except KeyError as exc:  # pragma: no cover - defensive branch
            available = ", ".join(sorted(self.stages)) or "<none>"
            raise KeyError(f"未配置名为 '{name}' 的流水线阶段，可用阶段: {available}") from exc

    def resolve(self, name: str, *, channel: str | None = None) -> StageSettings:
        stage = self.get(name)
        return stage if channel is None else stage.for_channel(channel)


@dataclass(slots=True)
class AppConfig:
    default_spider: str
    http: HttpSettings
    paths: PathSettings
    pipeline: PipelineSettings
    spiders: dict[str, dict[str, str]]

    def _stage_by_alias(self, *aliases: str, channel: str | None = None) -> StageSettings:
        for alias in aliases:
            if alias in self.pipeline.stages:
                stage = self.pipeline.stages[alias]
                return stage if channel is None else stage.for_channel(channel)
        available = ", ".join(sorted(self.pipeline.stages)) or "<none>"
        raise KeyError(f"未找到阶段 {aliases}，请检查 pipeline 配置 (当前可用: {available})")

    def get_stage(self, name: str, *, channel: str | None = None) -> StageSettings:
        return self.pipeline.resolve(name, channel=channel)

    @property
    def ai(self) -> StageSettings:
        return self._stage_by_alias("translate", "translation", "ai")

    def ai_for(self, channel: str | None) -> StageSettings:
        return self._stage_by_alias("translate", "translation", "ai", channel=channel)

    @property
    def formatting(self) -> StageSettings:
        return self._stage_by_alias("format", "formatting")

    def formatting_for(self, channel: str | None) -> StageSettings:
        return self._stage_by_alias("format", "formatting", channel=channel)

    @property
    def title(self) -> StageSettings:
        return self._stage_by_alias("title", "headline")

    def title_for(self, channel: str | None) -> StageSettings:
        return self._stage_by_alias("title", "headline", channel=channel)


def _to_path(value: str | None, *, fallback: Path) -> Path:
    if not value:
        return fallback
    candidate = Path(value)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _config_path(explicit: str | os.PathLike[str] | None = None) -> Path:
    candidate: Path
    if explicit:
        candidate = Path(explicit)
    else:
        env_value = os.environ.get(CONFIG_ENV_VAR)
        candidate = Path(env_value) if env_value else PROJECT_ROOT / DEFAULT_CONFIG_NAME
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("rb") as fp:
        return tomllib.load(fp)


def _ensure_directories(paths: Iterable[Path]) -> None:
    for directory in paths:
        directory.mkdir(parents=True, exist_ok=True)


def _as_template(value: Any | None, fallback: Path | str) -> str:
    base = value if value is not None else fallback
    if isinstance(base, Path):
        try:
            base = base.relative_to(PROJECT_ROOT)
        except ValueError:
            pass
        return str(base)
    return str(base)


def _resolve_template_to_path(template: str, *, channel: str | None, fallback: Path) -> Path:
    target = template
    if "{channel}" in target:
        if channel:
            target = target.format(channel=channel)
        else:
            return fallback
    return _to_path(target, fallback=fallback)


def _resolve_template_to_glob(
    template: str, *, channel: str | None, fallback: str | None
) -> str | None:
    if "{channel}" in template:
        if channel:
            return template.format(channel=channel)
        return fallback
    return template


def _build_stage(name: str, data: dict[str, Any], *, default_channel: str | None) -> StageSettings:
    kind = str(data.get("kind", name))
    model = data.get("model")

    prompt_fallback = _STAGE_FALLBACK_PROMPTS.get(name, PROJECT_ROOT / "prompts" / f"{name}.txt")
    output_fallback = _STAGE_FALLBACK_OUTPUT_DIRS.get(name, PROJECT_ROOT / "data" / name)
    input_fallback = _STAGE_FALLBACK_INPUTS.get(name)

    prompt_template = _as_template(data.get("prompt_path"), prompt_fallback)
    output_template = _as_template(data.get("output_dir"), output_fallback)
    input_template = (
        _as_template(data.get("input_glob"), input_fallback or "")
        if data.get("input_glob") is not None
        else (input_fallback or "")
    )

    prompt_path = _resolve_template_to_path(
        prompt_template, channel=default_channel, fallback=prompt_fallback
    )
    output_dir = _resolve_template_to_path(
        output_template, channel=default_channel, fallback=output_fallback
    )
    input_glob = _resolve_template_to_glob(
        str(input_template), channel=default_channel, fallback=input_fallback
    )

    timeout = float(data.get("timeout", 30)) if data.get("timeout") is not None else None
    thinking_raw = data.get("thinking_budget")
    thinking_budget: int | None
    if isinstance(thinking_raw, (int, float)):
        thinking_budget = int(thinking_raw)
    elif isinstance(thinking_raw, str) and thinking_raw.strip():
        thinking_budget = int(float(thinking_raw))
    else:
        thinking_budget = None
    target_language = data.get("target_language")
    if target_language is None and kind == "translation":
        target_language = "zh-CN"

    recognised = {
        "kind",
        "model",
        "prompt_path",
        "output_dir",
        "input_glob",
        "timeout",
        "thinking_budget",
        "target_language",
    }
    extra = {k: v for k, v in data.items() if k not in recognised}

    return StageSettings(
        name=name,
        kind=kind,
        model=model,
        prompt_path=prompt_path,
        output_dir=output_dir,
        input_glob=input_glob,
        timeout=timeout,
        thinking_budget=thinking_budget,
        target_language=target_language,
        prompt_template=prompt_template,
        output_dir_template=output_template,
        input_glob_template=str(input_template) if input_template else None,
        prompt_fallback=prompt_fallback,
        output_dir_fallback=output_fallback,
        input_glob_fallback=input_fallback,
        extra=extra,
    )


def load_config(config_path: str | os.PathLike[str] | None = None) -> AppConfig:
    path = _config_path(config_path)
    data = _load_toml(path)

    app_section = data.get("app", {})
    paths_section = data.get("paths", {})
    http_section = data.get("http", {})
    pipeline_section = data.get("pipeline", {})
    stages_section = pipeline_section.get("stages", {})

    data_dir = _to_path(paths_section.get("data_dir"), fallback=PROJECT_ROOT / "data")
    log_dir = _to_path(paths_section.get("log_dir"), fallback=data_dir / "logs")
    state_dir = _to_path(paths_section.get("state_dir"), fallback=data_dir / "state")
    cookie_path = _to_path(paths_section.get("cookie_jar"), fallback=state_dir / "cookies.txt")
    header_path = _to_path(paths_section.get("header_jar"), fallback=state_dir / "headers.json")

    configured_channel = pipeline_section.get("default_channel")
    default_channel = configured_channel or app_section.get("default_spider")
    channel_root = data_dir / (default_channel or "default")
    raw_dir = _to_path(paths_section.get("raw_dir"), fallback=channel_root / "raw")
    translated_dir = _to_path(
        paths_section.get("translated_dir"), fallback=channel_root / "translated"
    )
    formatted_dir = _to_path(
        paths_section.get("formatted_dir"), fallback=channel_root / "formatted"
    )
    titles_dir = _to_path(paths_section.get("titles_dir"), fallback=channel_root / "titles")
    artifacts_value = paths_section.get("artifacts_dir") or paths_section.get("processed_dir")
    artifacts_dir = _to_path(artifacts_value, fallback=channel_root / "artifacts")

    _ensure_directories(
        (
            data_dir,
            channel_root,
            raw_dir,
            translated_dir,
            formatted_dir,
            titles_dir,
            artifacts_dir,
            log_dir,
            state_dir,
            cookie_path.parent,
            header_path.parent,
        )
    )

    http_settings = HttpSettings(
        timeout=float(http_section.get("timeout", 10)),
        min_delay=float(http_section.get("min_delay", 0)),
        max_delay=float(http_section.get("max_delay", 0)),
        max_attempts=int(http_section.get("max_attempts", 3)),
        backoff_factor=float(http_section.get("backoff_factor", 1.5)),
    )

    default_channel = pipeline_section.get("default_channel")
    stages = {
        name: _build_stage(name, stage_data, default_channel=default_channel)
        for name, stage_data in stages_section.items()
    }

    pipeline_settings = PipelineSettings(
        default_channel=default_channel,
        stages=stages,
    )

    spiders_list = data.get("spiders", [])
    spiders: dict[str, dict[str, str]] = {}
    for item in spiders_list:
        name = item.get("name")
        if not name:
            continue
        spiders[name] = {k: v for k, v in item.items() if k != "name"}

    config = AppConfig(
        default_spider=app_section.get("default_spider", "example"),
        http=http_settings,
        paths=PathSettings(
            data_dir=data_dir,
            raw_dir=raw_dir,
            translated_dir=translated_dir,
            formatted_dir=formatted_dir,
            titles_dir=titles_dir,
            artifacts_dir=artifacts_dir,
            log_dir=log_dir,
            state_dir=state_dir,
            cookie_jar=cookie_path,
            header_jar=header_path,
            default_channel=default_channel,
        ),
        pipeline=pipeline_settings,
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
