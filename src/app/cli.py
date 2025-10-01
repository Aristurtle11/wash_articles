"""Unified command-line interface for crawlers and pipeline automation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable, Iterable, Sequence

from ..settings import AppConfig, load_config
from ..utils.logging import configure_logging, get_logger
from .pipeline import PipelineContext, PipelineHooks, PipelineRunner, build_default_runner
from .pipeline_state import PipelineState, PipelineStateStore
from .runner import run as run_spider

LOGGER = get_logger(__name__)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    configure_logging(structured=not args.log_plain)

    if getattr(args, "legacy_spider", None):
        LOGGER.warning(
            "Using legacy spider flag; consider 'wash spider run --spider <name>'",
            extra={"event": "cli.deprecated", "flag": "--spider"},
        )
        run_spider(["--spider", args.legacy_spider, *(args.config and ["--config", args.config] or [])])
        return 0

    handler: Callable[[argparse.Namespace], int] | None = getattr(args, "handler", None)
    if handler is None:
        parser.print_help(sys.stderr)
        return 1
    return handler(args)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wash", description="wash_articles CLI")
    parser.add_argument("--config", help="Path to configuration file", default=None)
    parser.add_argument(
        "--log-plain",
        action="store_true",
        help="Use plain-text logs instead of JSON",
    )
    parser.add_argument(
        "--spider",
        dest="legacy_spider",
        help=argparse.SUPPRESS,
    )

    subparsers = parser.add_subparsers(dest="command")

    _add_spider_commands(subparsers)
    _add_pipeline_commands(subparsers)

    return parser


def _add_spider_commands(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    spider_parser = subparsers.add_parser("spider", help="Run a configured spider")
    spider_subparsers = spider_parser.add_subparsers(dest="spider_command", required=True)

    run_parser = spider_subparsers.add_parser("run", help="Execute a spider and emit JSONL output")
    run_parser.add_argument("--spider", required=False, help="Spider name; defaults to config default")
    run_parser.set_defaults(handler=_handle_spider_run)


def _add_pipeline_commands(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    pipeline_parser = subparsers.add_parser("pipeline", help="End-to-end content pipeline")
    pipeline_parser.add_argument("--channel", help="Channel name to operate on", default=None)
    pipeline_parser.add_argument(
        "--api-key",
        dest="api_key",
        help="API key override passed to AI stages",
        default=None,
    )
    pipeline_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Regenerate outputs even if files already exist",
    )
    pipeline_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Avoid mutating remote systems (e.g., skip real publish)",
    )

    pipeline_subparsers = pipeline_parser.add_subparsers(dest="pipeline_command", required=True)

    run_parser = pipeline_subparsers.add_parser("run", help="Run the full pipeline from scratch")
    run_parser.add_argument(
        "--only",
        nargs="+",
        metavar="STEP",
        help="Limit execution to specific steps",
    )
    run_parser.set_defaults(handler=_handle_pipeline_run)

    resume_parser = pipeline_subparsers.add_parser("resume", help="Resume from the last incomplete step")
    resume_parser.add_argument(
        "--only",
        nargs="+",
        metavar="STEP",
        help="Restrict resume to the provided steps",
    )
    resume_parser.set_defaults(handler=_handle_pipeline_resume)

    inspect_parser = pipeline_subparsers.add_parser("inspect", help="Show stored pipeline state")
    inspect_parser.add_argument(
        "--format",
        choices=("json", "table"),
        default="json",
        help="Output format for state inspection",
    )
    inspect_parser.set_defaults(handler=_handle_pipeline_inspect)

    clean_parser = pipeline_subparsers.add_parser("clean", help="Reset pipeline state")
    clean_parser.add_argument(
        "--outputs",
        action="store_true",
        help="Also clear translated/formatted/title outputs",
    )
    clean_parser.set_defaults(handler=_handle_pipeline_clean)


def _handle_spider_run(args: argparse.Namespace) -> int:
    argv: list[str] = []
    if args.spider:
        argv.extend(["--spider", args.spider])
    if args.config:
        argv.extend(["--config", args.config])
    LOGGER.info(
        "Launching spider",
        extra={"event": "cli.command", "command": "spider.run", "spider": args.spider or "<default>"},
    )
    run_spider(argv)
    return 0


def _handle_pipeline_run(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    runner, context = build_default_runner(
        config=config,
        channel=args.channel,
        api_key=args.api_key,
        overwrite=args.overwrite,
        dry_run=args.dry_run,
    )
    state_store = PipelineStateStore(_state_root(config))
    state = PipelineState.initialize(context.channel, runner.step_names)
    state_store.save(state)

    LOGGER.info(
        "Pipeline run started",
        extra={
            "event": "cli.command",
            "command": "pipeline.run",
            "channel": context.channel,
            "steps": list(runner.step_names),
        },
    )

    hooks = _build_hooks(state_store, state)
    selection = _select_steps(runner, args.only)

    try:
        runner.run(context, only=selection, hooks=hooks)
    except Exception:
        LOGGER.error(
            "Pipeline run failed",
            extra={"event": "cli.command", "command": "pipeline.run", "channel": context.channel},
        )
        raise

    LOGGER.info(
        "Pipeline run finished",
        extra={"event": "cli.command", "command": "pipeline.run", "channel": context.channel},
    )
    return 0


def _handle_pipeline_resume(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    runner, context = build_default_runner(
        config=config,
        channel=args.channel,
        api_key=args.api_key,
        overwrite=args.overwrite,
        dry_run=args.dry_run,
    )
    state_store = PipelineStateStore(_state_root(config))
    state = state_store.load(context.channel)
    if state is None:
        LOGGER.error(
            "No previous pipeline run found",
            extra={"event": "cli.error", "command": "pipeline.resume", "channel": context.channel},
        )
        raise SystemExit(2)

    state.reset_incomplete()
    completed = set(state.completed_steps())
    pending = [step for step in runner.step_names if step not in completed]
    if not pending:
        LOGGER.info(
            "All pipeline steps already completed",
            extra={"event": "cli.command", "command": "pipeline.resume", "channel": context.channel},
        )
        return 0

    selection = _select_steps(runner, args.only)
    if selection is None:
        selection = pending
    else:
        selection = [step for step in selection if step in pending]

    if not selection:
        LOGGER.info(
            "No matching steps to resume",
            extra={"event": "cli.command", "command": "pipeline.resume", "channel": context.channel},
        )
        return 0

    LOGGER.info(
        "Resuming pipeline",
        extra={
            "event": "cli.command",
            "command": "pipeline.resume",
            "channel": context.channel,
            "remaining": selection,
        },
    )

    hooks = _build_hooks(state_store, state)
    runner.run(context, only=selection, completed=completed, hooks=hooks)

    LOGGER.info(
        "Resume completed",
        extra={"event": "cli.command", "command": "pipeline.resume", "channel": context.channel},
    )
    return 0


def _handle_pipeline_inspect(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    channel = _resolve_channel(config, args.channel)
    state_store = PipelineStateStore(_state_root(config))
    state = state_store.load(channel)
    if state is None:
        LOGGER.warning(
            "No pipeline state recorded",
            extra={"event": "cli.command", "command": "pipeline.inspect", "channel": channel},
        )
        print("<no-state>")
        return 0

    if args.format == "table":
        _print_state_table(state)
    else:
        print(json.dumps(state.to_dict(), ensure_ascii=False, indent=2))
    return 0


def _handle_pipeline_clean(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    channel = _resolve_channel(config, args.channel)
    state_store = PipelineStateStore(_state_root(config))
    state_store.delete(channel)

    LOGGER.info(
        "Cleared pipeline state",
        extra={"event": "cli.command", "command": "pipeline.clean", "channel": channel},
    )

    if args.outputs:
        context_root = config.paths.channel_root(channel)
        _clear_outputs(config, channel)
        LOGGER.info(
            "Removed generated outputs",
            extra={
                "event": "cli.command",
                "command": "pipeline.clean",
                "channel": channel,
                "paths": {
                    "translated": str(config.paths.translated_for(channel)),
                    "formatted": str(config.paths.formatted_for(channel)),
                    "titles": str(config.paths.titles_for(channel)),
                },
            },
        )
        print(f"Outputs cleared under {context_root}")
    return 0


def _select_steps(runner: PipelineRunner, requested: Iterable[str] | None) -> list[str] | None:
    if requested is None:
        return None

    available = {name.lower(): name for name in runner.step_names}
    desired = [name.lower() for name in requested]
    invalid = [name for name in desired if name not in available]
    if invalid:
        LOGGER.error(
            "Unknown pipeline steps provided",
            extra={"event": "cli.error", "invalid_steps": sorted(set(invalid))},
        )
        raise SystemExit(2)

    selected_keys = set(desired)

    # Ensure dependencies are included even if not explicitly requested.
    changed = True
    while changed:
        changed = False
        for step in runner.steps:
            name_key = step.name.lower()
            if name_key in selected_keys:
                for dep in step.depends_on:
                    dep_key = dep.lower()
                    if dep_key not in selected_keys:
                        selected_keys.add(dep_key)
                        changed = True

    return [name for name in runner.step_names if name.lower() in selected_keys]


def _build_hooks(store: PipelineStateStore, state: PipelineState) -> PipelineHooks:
    def before(step: str, _: PipelineContext) -> None:
        state.mark_running(step)
        store.save(state)

    def after(step: str, _: PipelineContext) -> None:
        state.mark_completed(step)
        store.save(state)

    def error(step: str, _: PipelineContext, exc: BaseException) -> None:
        state.mark_failed(step)
        store.save(state)
        LOGGER.debug(
            "Exception captured",
            extra={"event": "pipeline.error", "step": step, "error_type": type(exc).__name__},
        )

    return PipelineHooks(before_step=before, after_step=after, on_error=error)


def _resolve_channel(config: AppConfig, override: str | None) -> str:
    if override:
        return override
    return config.pipeline.default_channel or config.default_spider


def _state_root(config: AppConfig) -> Path:
    return config.paths.state_dir / "pipeline"


def _print_state_table(state: PipelineState) -> None:
    width = max((len(name) for name in state.steps), default=8)
    print("Step".ljust(width), "Status", sep="  ")
    for name, status in state.steps.items():
        print(name.ljust(width), status, sep="  ")


def _clear_outputs(config: AppConfig, channel: str) -> None:
    for path in (
        config.paths.translated_for(channel),
        config.paths.formatted_for(channel),
        config.paths.titles_for(channel),
    ):
        if path.exists():
            for child in path.iterdir():
                if child.is_dir():
                    _remove_tree(child)
                else:
                    child.unlink()
        else:
            path.mkdir(parents=True, exist_ok=True)


def _remove_tree(path: Path) -> None:
    for child in path.iterdir():
        if child.is_dir():
            _remove_tree(child)
        else:
            child.unlink()
    path.rmdir()


__all__ = ["main"]
