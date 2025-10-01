"""Persistence helpers for pipeline execution state."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slugify(value: str) -> str:
    lowered = value.lower()
    safe = [ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in lowered]
    slug = "".join(safe).strip("-")
    return slug or "default"


@dataclass(slots=True)
class PipelineState:
    """Represents step progress for a specific channel."""

    channel: str
    steps: dict[str, str]
    updated_at: str = field(default_factory=_now)
    run_id: str | None = None

    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"

    @classmethod
    def initialize(
        cls, channel: str, step_names: Iterable[str], *, run_id: str | None = None
    ) -> "PipelineState":
        steps = {name: cls.STATUS_PENDING for name in step_names}
        return cls(channel=channel, steps=steps, run_id=run_id or _now())

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "PipelineState":
        channel = str(data.get("channel", "default"))
        raw_steps = data.get("steps", {})
        if not isinstance(raw_steps, dict):  # pragma: no cover - defensive
            raise ValueError("Invalid pipeline state: 'steps' must be a mapping")
        steps: dict[str, str] = {str(name): str(status) for name, status in raw_steps.items()}
        updated_at = str(data.get("updated_at", _now()))
        run_id = data.get("run_id")
        return cls(
            channel=channel,
            steps=steps,
            updated_at=updated_at,
            run_id=str(run_id) if run_id else None,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "channel": self.channel,
            "steps": self.steps,
            "updated_at": self.updated_at,
            "run_id": self.run_id,
        }

    def mark_running(self, step: str) -> None:
        self.steps[step] = self.STATUS_RUNNING
        self.updated_at = _now()

    def mark_completed(self, step: str) -> None:
        self.steps[step] = self.STATUS_COMPLETED
        self.updated_at = _now()

    def mark_failed(self, step: str) -> None:
        self.steps[step] = self.STATUS_FAILED
        self.updated_at = _now()

    def reset_incomplete(self) -> None:
        for name, status in self.steps.items():
            if status != self.STATUS_COMPLETED:
                self.steps[name] = self.STATUS_PENDING
        self.updated_at = _now()

    def completed_steps(self) -> list[str]:
        return [name for name, status in self.steps.items() if status == self.STATUS_COMPLETED]

    def pending_steps(self) -> list[str]:
        return [name for name, status in self.steps.items() if status != self.STATUS_COMPLETED]


class PipelineStateStore:
    """Stores pipeline state on disk under the configured state directory."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def path_for(self, channel: str) -> Path:
        return self._root / f"{_slugify(channel)}.json"

    def load(self, channel: str) -> PipelineState | None:
        path = self.path_for(channel)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        state = PipelineState.from_dict(data)
        # Preserve the original channel name even if slugified path differs.
        state.channel = channel
        return state

    def save(self, state: PipelineState) -> Path:
        path = self.path_for(state.channel)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def delete(self, channel: str) -> None:
        path = self.path_for(channel)
        if path.exists():
            path.unlink()


__all__ = ["PipelineState", "PipelineStateStore"]
