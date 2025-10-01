"""Upload images and publish a WeChat draft for a translated article."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.settings import load_config
from src.platforms import ContentBundle
from src.platforms.wechat import (
    WeChatApiClient,
    WeChatApiError,
    WeChatCredentialStore,
    WeChatDraftClient,
    WeChatMediaUploader,
)
from src.services.publishing_helper import (
    collect_images,
    resolve_title,
    select_article,
)
from src.services.wechat_components import ContentBuilder, PayloadBuilder
from src.services.wechat_models import ArticleMetadata
from src.services.wechat_workflow import WeChatArticleWorkflow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Upload images and publish a WeChat article draft"
    )
    parser.add_argument(
        "--channel", required=True, help="Channel/spider identifier, e.g., realtor"
    )
    parser.add_argument(
        "--article",
        type=Path,
        help="Specific translated article file; defaults to the newest .txt under the channel",
    )
    parser.add_argument("--title", help="Article title; defaults to AI-generated")
    parser.add_argument("--author", help="Author name")
    parser.add_argument("--digest", help="Summary; defaults to the first 120 chars")
    parser.add_argument("--source-url", help="Original source URL")
    parser.add_argument(
        "--open-comment", action="store_true", help="Enable comments for the article"
    )
    parser.add_argument(
        "--fans-only-comment",
        action="store_true",
        help="Restrict comments to fans only",
    )
    parser.add_argument(
        "--token-cache",
        default=Path("data/state/wechat_token.json"),
        type=Path,
        help="Path for caching access tokens",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate payload without calling WeChat API",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    app_config = load_config()
    channel = args.channel
    translated_root = app_config.paths.translated_for(channel)
    raw_root = app_config.paths.raw_for(channel)

    try:
        article_path = args.article or select_article(translated_root)
        if not article_path.is_file():
            raise SystemExit(f"指定的文章不存在: {article_path}")

        images = collect_images(raw_root)

        title = resolve_title(
            article_path,
            translated_root,
            channel,
            app_config,
            override=args.title,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(f"数据准备失败: {exc}") from exc

    metadata = ArticleMetadata(
        channel=channel,
        article_path=article_path,
        title=title,
        author=args.author,
        digest=args.digest,
        source_url=args.source_url,
        need_open_comment=args.open_comment,
        only_fans_can_comment=args.fans_only_comment,
    )

    api_client = WeChatApiClient()
    credential_store = WeChatCredentialStore(
        token_cache_path=args.token_cache, api_client=api_client
    )
    media_uploader = WeChatMediaUploader(credential_store)
    draft_client = WeChatDraftClient(credential_store)

    content_builder = ContentBuilder()
    payload_builder = PayloadBuilder()
    workflow = WeChatArticleWorkflow(
        media_uploader,
        draft_client,
        content_builder,
        payload_builder,
    )

    bundle = ContentBundle(channel=channel, article_path=article_path, images=images)

    try:
        result = workflow.publish(bundle, metadata, dry_run=args.dry_run)
    except (WeChatApiError, RuntimeError, FileNotFoundError) as exc:
        raise SystemExit(f"发布失败: {exc}") from exc

    print("草稿创建成功")
    print("media_id:", result.media_id)
    print("封面素材ID:", result.uploads[0].media_id)
    print("使用图片:")
    for item in result.uploads:
        print(f"  - {item.local_path.name}: {item.media_id} -> {item.remote_url}")

    if args.dry_run:
        print("提交的JSON (Dry Run):")
        print(json.dumps(result.payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
