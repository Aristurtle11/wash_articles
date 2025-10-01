"""Tests for the pipeline runner orchestration helpers."""

from __future__ import annotations

import pytest

from src.app.pipeline import PipelineHooks, PipelineRunner, PipelineStep


def test_runner_skips_completed_steps() -> None:
    order: list[str] = []

    steps = [
        PipelineStep("fetch", lambda ctx: order.append("fetch")),
        PipelineStep("translate", lambda ctx: order.append("translate"), depends_on=("fetch",)),
    ]
    runner = PipelineRunner(steps)

    runner.run(object(), completed={"fetch"})

    assert order == ["translate"]


def test_runner_invokes_hooks_and_propagates_errors() -> None:
    events: list[str] = []

    def step_a(_: object) -> None:
        events.append("run:a")

    def step_b(_: object) -> None:
        events.append("run:b")
        raise RuntimeError("boom")

    hooks = PipelineHooks(
        before_step=lambda name, _: events.append(f"before:{name}"),
        after_step=lambda name, _: events.append(f"after:{name}"),
        on_error=lambda name, _, exc: events.append(f"error:{name}:{type(exc).__name__}"),
    )

    steps = [
        PipelineStep("a", step_a),
        PipelineStep("b", step_b, depends_on=("a",)),
    ]
    runner = PipelineRunner(steps)

    with pytest.raises(RuntimeError):
        runner.run(object(), hooks=hooks)

    assert events == [
        "before:a",
        "run:a",
        "after:a",
        "before:b",
        "run:b",
        "error:b:RuntimeError",
    ]
