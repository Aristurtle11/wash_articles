"""Tests for pipeline state persistence helpers."""

from __future__ import annotations

from pathlib import Path

from src.app.pipeline_state import PipelineState, PipelineStateStore


def test_pipeline_state_transitions() -> None:
    state = PipelineState.initialize("demo", ["fetch", "translate", "publish"], run_id="test")

    assert state.pending_steps() == ["fetch", "translate", "publish"]

    state.mark_running("fetch")
    state.mark_completed("fetch")
    assert state.completed_steps() == ["fetch"]

    state.mark_failed("publish")
    assert set(state.pending_steps()) == {"translate", "publish"}

    state.reset_incomplete()
    assert state.steps["publish"] == PipelineState.STATUS_PENDING


def test_pipeline_state_store_roundtrip(tmp_path: Path) -> None:
    store = PipelineStateStore(tmp_path)
    state = PipelineState.initialize("Channel/Name", ["fetch", "translate"])
    store.save(state)

    saved_path = store.path_for("Channel/Name")
    assert saved_path.exists()
    assert saved_path.name.endswith(".json")

    loaded = store.load("Channel/Name")
    assert loaded is not None
    assert loaded.channel == "Channel/Name"
    assert loaded.steps == state.steps
