"""Format translated articles into HTML using Gemini."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path
from typing import Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ai import Formatter, FormattingConfig
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
    parser = argparse.ArgumentParser(description="Format translated articles into HTML")
    parser.add_argument("--input", nargs="*", help="Glob patterns for translated files")
    parser.add_argument("--prompt", help="Override prompt file path")
    parser.add_argument("--output-dir", help="Directory for formatted HTML")
    parser.add_argument("--model", help="Gemini model name")
    parser.add_argument("--channel", help="Logical channel (defaults to pipeline.default_channel)")
    parser.add_argument("--timeout", type=float, help="Request timeout in seconds")
    parser.add_argument("--relative-to", help="Preserve structure relative to this base path")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing formatted files")
    parser.add_argument("--api-key", help="Gemini API key (falls back to GEMINI_API_KEY env var)")
    parser.add_argument("--thinking-budget", type=int, help="Enable Gemini thinking mode with given budget")
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    app_config = load_config()  # ensure config.toml is validated and directories created
    channel = args.channel or app_config.pipeline.default_channel or app_config.paths.default_channel or app_config.default_spider
    cfg = FormattingConfig.from_app_config(channel=channel)

    if args.prompt:
        cfg = replace(cfg, prompt_path=Path(args.prompt))
    if args.output_dir:
        cfg = replace(cfg, output_dir=Path(args.output_dir))
    if args.model:
        cfg = replace(cfg, model=args.model)
    if args.timeout:
        cfg = replace(cfg, timeout=args.timeout)
    if args.thinking_budget is not None:
        cfg = replace(cfg, thinking_budget=args.thinking_budget)

    patterns = args.input or [cfg.input_glob]
    files = _collect_files(patterns)
    if not files:
        LOGGER.info("No files to format. Exiting.")
        return

    relative_base = (
        Path(args.relative_to).resolve()
        if args.relative_to
        else app_config.paths.translated_for(channel).resolve()
    )

    formatter = Formatter.from_config(
        config=cfg,
        overwrite=bool(args.overwrite),
        relative_to=relative_base,
        api_key=args.api_key,
    )
    formatter.format_many(files)


if __name__ == "__main__":
    main()
