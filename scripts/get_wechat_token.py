"""Fetch and display a fresh WeChat access token."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.platforms.wechat.api import WeChatApiClient, WeChatApiError
from src.platforms.wechat.credentials import WeChatCredentialStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Get a WeChat access token using environment credentials"
    )
    parser.add_argument(
        "--token-cache",
        default=Path("data/state/wechat_token.json"),
        type=Path,
        help="Path for caching token metadata (optional)",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Ignore缓存强制向微信获取新的 access_token",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    api_client = WeChatApiClient()
    store = WeChatCredentialStore(token_cache_path=args.token_cache, api_client=api_client)

    try:
        token = store.get_token(force_refresh=args.force_refresh)
    except WeChatApiError as exc:
        details = " ".join(f"{k}={v}" for k, v in exc.details.items()) if exc.details else ""
        raise SystemExit(f"获取 access_token 失败：{exc}. {details}") from exc
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    print("access_token:", token.value)
    print("expires_at:", token.expires_at.isoformat())


if __name__ == "__main__":
    main()
