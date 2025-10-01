"""Tests for CLI helper utilities."""

from __future__ import annotations

import pytest

from src.app import cli
from src.app.pipeline import PipelineRunner, PipelineStep


def _build_runner() -> PipelineRunner:
    steps = [
        PipelineStep("fetch", lambda ctx: None),
        PipelineStep("translate", lambda ctx: None, depends_on=("fetch",)),
        PipelineStep("format", lambda ctx: None, depends_on=("translate",)),
        PipelineStep("title", lambda ctx: None, depends_on=("translate",)),
        PipelineStep("publish", lambda ctx: None, depends_on=("format", "title")),
    ]
    return PipelineRunner(steps)


def test_select_steps_includes_dependencies() -> None:
    runner = _build_runner()
    selection = cli._select_steps(runner, ["publish"])
    assert selection == ["fetch", "translate", "format", "title", "publish"]


def test_select_steps_validates_names() -> None:
    runner = _build_runner()
    with pytest.raises(SystemExit) as excinfo:
        cli._select_steps(runner, ["unknown"])
    assert excinfo.value.code == 2
