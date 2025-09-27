#!/usr/bin/env python
"""Translate text files using Gemini."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path
from typing import Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ai import TranslationConfig, Translator
from src.settings import load_config
from src.utils.logging import configure_logging, get_logger

LOGGER = get_logger(__name__)


def _collect_files(patterns: Sequence[str]) -> list[Path]:
    files: list[Path] = []
    for pattern in patterns:
        matched = sorted(Path().glob(pattern))
        if not matched:
            LOGGER.warning("No files matched pattern %s", pattern)
        files.extend(path for path in matched if path.is_file())
    return files


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Translate text files using Gemini")
    parser.add_argument("--input", nargs="*", help="Glob patterns for source files")
    parser.add_argument("--prompt", help="Override prompt file path")
    parser.add_argument("--output-dir", help="Directory for translated files")
    parser.add_argument("--model", help="Gemini model name")
    parser.add_argument("--language", help="Target language (default from config)")
    parser.add_argument("--relative-to", help="Base path to preserve directory structure")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing translations")
    parser.add_argument("--api-key", help="Gemini API key (falls back to GEMINI_API_KEY env var)")
    parser.add_argument("--timeout", type=float, help="Request timeout in seconds")
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    app_config = load_config()
    cfg = TranslationConfig.from_app_config()

    if args.prompt:
        cfg = replace(cfg, prompt_path=Path(args.prompt))
    if args.output_dir:
        cfg = replace(cfg, output_dir=Path(args.output_dir))
    if args.model:
        cfg = replace(cfg, model=args.model)
    if args.language:
        cfg = replace(cfg, target_language=args.language)
    if args.timeout:
        cfg = replace(cfg, timeout=args.timeout)

    patterns = args.input or [cfg.input_glob]
    files = _collect_files(patterns)
    if not files:
        LOGGER.info("No files to translate. Exiting.")
        return

    relative_base = Path(args.relative_to).resolve() if args.relative_to else app_config.paths.raw_dir.resolve()
    translator = Translator.from_config(
        api_key=args.api_key,
        config=cfg,
        overwrite=bool(args.overwrite),
        relative_to=relative_base,
    )
    translator.translate_many(files)


if __name__ == "__main__":
    main()
