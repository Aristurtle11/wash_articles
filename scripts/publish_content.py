"""Command-line entrypoint for publishing content bundles."""

from __future__ import annotations

import argparse
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Publish translated content to a platform")
    parser.add_argument("--platform", required=True, help="Target platform identifier, e.g., wechat")
    parser.add_argument("--channel", required=True, help="Content channel or spider name")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run workflow without performing network operations",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    platform = args.platform.lower()
    channel = args.channel
    _ = (platform, channel)
    translated_root = Path(f"data/{channel}/translated")
    raw_root = Path(f"data/{channel}/raw")
    dry_run = bool(args.dry_run)
    _ = (translated_root, raw_root, dry_run)
    # TODO: Wire up service, factories, and execute workflow.


if __name__ == "__main__":
    main()
