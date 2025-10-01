"""Convert legacy INI configuration into the new TOML layout."""

from __future__ import annotations

import argparse
from configparser import ConfigParser
from pathlib import Path
from typing import Iterable

_STAGE_MAP = {
    "ai": ("translate", "translation"),
    "formatting": ("format", "formatting"),
    "title": ("title", "title"),
}


def _read_ini(path: Path) -> ConfigParser:
    parser = ConfigParser()
    with path.open("r", encoding="utf-8") as fp:
        parser.read_file(fp)
    return parser


def _value(section: ConfigParser, key: str, default: str | None = None) -> str | None:
    return section.get(key) if section and section.get(key) is not None else default


def _emit_header(lines: list[str], header: str) -> None:
    if lines and lines[-1] != "":
        lines.append("")
    lines.append(f"[{header}]")


def _emit_kv(lines: list[str], key: str, value: str | None) -> None:
    if value is None:
        return
    lines.append(f"{key} = {value}")


def _quote(value: str | None) -> str | None:
    if value is None:
        return None
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _emit_stage(lines: list[str], stage_name: str, data: dict[str, str | None]) -> None:
    _emit_header(lines, f"pipeline.stages.{stage_name}")
    for key, value in (
        ("kind", _quote(data.get("kind"))),
        ("model", _quote(data.get("model"))),
        ("prompt_path", _quote(data.get("prompt_path"))),
        ("output_dir", _quote(data.get("output_dir"))),
        ("input_glob", _quote(data.get("input_glob"))),
        ("target_language", _quote(data.get("target_language"))),
        ("timeout", data.get("timeout")),
        ("thinking_budget", data.get("thinking_budget")),
    ):
        _emit_kv(lines, key, value)


def _emit_spiders(lines: list[str], spiders: Iterable[tuple[str, dict[str, str]]]) -> None:
    for name, params in spiders:
        lines.append("")
        lines.append("[[spiders]]")
        lines.append(f"name = {_quote(name)}")
        for key, value in params.items():
            lines.append(f"{key} = {_quote(value)}")


def migrate(input_path: Path, output_path: Path, *, default_channel: str | None) -> None:
    parser = _read_ini(input_path)

    app_section = parser["app"] if parser.has_section("app") else {}
    paths_section = parser["paths"] if parser.has_section("paths") else {}
    http_section = parser["http"] if parser.has_section("http") else {}

    lines: list[str] = []
    _emit_header(lines, "app")
    _emit_kv(lines, "default_spider", _quote(_value(app_section, "default_spider", "example")))

    _emit_header(lines, "paths")
    for key in ("data_dir", "raw_dir", "processed_dir", "log_dir", "state_dir", "cookie_jar"):
        _emit_kv(lines, key, _quote(_value(paths_section, key)))

    _emit_header(lines, "http")
    for key in ("min_delay", "max_delay", "max_attempts", "backoff_factor", "timeout"):
        _emit_kv(lines, key, _value(http_section, key))

    _emit_header(lines, "pipeline")
    chosen_channel = default_channel or parser.get("pipeline", "default_channel", fallback=None)
    if not chosen_channel:
        chosen_channel = _value(app_section, "default_spider", "example")
    _emit_kv(lines, "default_channel", _quote(chosen_channel))

    for section_name, (stage_name, kind) in _STAGE_MAP.items():
        stage_section = parser[section_name] if parser.has_section(section_name) else {}
        stage_data = {
            "kind": kind,
            "model": _value(stage_section, "model"),
            "prompt_path": _value(stage_section, "prompt_path"),
            "output_dir": _value(stage_section, "output_dir"),
            "input_glob": _value(stage_section, "input_glob"),
            "target_language": _value(stage_section, "target_language"),
            "timeout": _value(stage_section, "timeout"),
            "thinking_budget": _value(stage_section, "thinking_budget"),
        }
        _emit_stage(lines, stage_name, stage_data)

    spiders = []
    for section in parser.sections():
        if section.lower().startswith("spider:"):
            name = section.split(":", 1)[1].strip()
            spiders.append(
                (
                    name,
                    {k: v for k, v in parser[section].items()},
                )
            )

    _emit_spiders(lines, spiders)

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert config.ini to config.toml")
    parser.add_argument(
        "--input", default="config.ini", type=Path, help="Path to legacy INI config"
    )
    parser.add_argument(
        "--output", default="config.toml", type=Path, help="Destination TOML config"
    )
    parser.add_argument(
        "--default-channel",
        help="Override pipeline.default_channel when migrating",
    )
    args = parser.parse_args()

    migrate(args.input, args.output, default_channel=args.default_channel)
    print(f"已生成 {args.output}，请确认后删除旧的 config.ini")


if __name__ == "__main__":
    main()
