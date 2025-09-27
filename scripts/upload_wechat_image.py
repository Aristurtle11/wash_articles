"""Upload channel image_001.jpg as permanent WeChat material."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.platforms import ContentBundle
from src.platforms.wechat import WeChatApiClient, WeChatCredentialStore, WeChatMediaUploader, WeChatApiError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Upload image_001.jpg to WeChat as permanent material")
    parser.add_argument("--channel", required=True, help="Channel/spider identifier, e.g., realtor")
    parser.add_argument(
        "--raw-root",
        default=Path("data/raw"),
        type=Path,
        help="Root directory containing raw assets",
    )
    parser.add_argument(
        "--token-cache",
        default=Path("data/state/wechat_token.json"),
        type=Path,
        help="Path for caching WeChat access tokens",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="强制刷新 access_token 后再上传",
    )
    return parser


def locate_images(raw_root: Path, channel: str) -> list[Path]:
    image_dir = raw_root / channel / "images"
    if not image_dir.is_dir():
        raise FileNotFoundError(f"未找到图片目录: {image_dir}")
    candidates = sorted(p for p in image_dir.iterdir() if p.is_file())
    if not candidates:
        raise FileNotFoundError(f"目录 {image_dir} 中未找到任何图片文件")
    return candidates


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    image_paths = locate_images(args.raw_root, args.channel)

    api_client = WeChatApiClient()
    store = WeChatCredentialStore(token_cache_path=args.token_cache, api_client=api_client)

    try:
        store.get_token(force_refresh=args.force_refresh)
    except (WeChatApiError, RuntimeError) as exc:
        raise SystemExit(f"无法获取 access_token: {exc}") from exc

    uploader = WeChatMediaUploader(store)
    bundle = ContentBundle(channel=args.channel, article_path=image_paths[0], images=image_paths)

    try:
        results = list(uploader.upload_batch(bundle))
    except WeChatApiError as exc:
        details = " ".join(f"{k}={v}" for k, v in exc.details.items()) if exc.details else ""
        raise SystemExit(f"上传失败: {exc}. {details}") from exc

    if not results:
        raise SystemExit("未找到需要上传的图片或上传流程被跳过")

    print("上传成功，共处理", len(results), "张图片：")
    for result in results:
        print("-", result.local_path.name)
        print("  素材ID:", result.media_id)
        print("  远程URL:", result.remote_url)


if __name__ == "__main__":
    main()
