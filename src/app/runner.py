"""Command-line entry point for running spiders."""

from __future__ import annotations

import argparse
from typing import Sequence

from ..core.http_client import HttpClient
from ..pipelines import DataSaverPipeline, TransformPipeline
from ..settings import load_config, load_default_headers
from ..spiders import get_spider
from ..utils.logging import configure_logging, get_logger

LOGGER = get_logger(__name__)


def run(argv: Sequence[str] | None = None) -> None:
    configure_logging(structured=None)
    parser = argparse.ArgumentParser(prog="wash", description="wash_articles crawler runner")
    parser.add_argument("--spider", help="Spider name to execute")
    parser.add_argument("--config", help="Path to the config file", default=None)
    args = parser.parse_args(argv)

    config = load_config(args.config)
    spider_name = args.spider or config.default_spider

    LOGGER.info("Starting spider %s", spider_name)

    default_headers = load_default_headers()
    client = HttpClient(
        http_settings=config.http,
        cookie_path=config.paths.cookie_jar,
        default_headers=default_headers,
    )

    SpiderClass = get_spider(spider_name)
    spider_config = config.spiders.get(spider_name, {})
    pipelines = [
        TransformPipeline(),
        DataSaverPipeline(config.paths.artifacts_for(spider_name), filename=f"{spider_name}.jsonl"),
    ]

    spider = SpiderClass(client, pipelines, config=spider_config)
    spider.run()

    LOGGER.info("Spider %s completed", spider_name)
