"""Data cleaning pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .base_pipeline import BasePipeline


class TransformPipeline(BasePipeline):
    """Attach housekeeping metadata to dictionary items."""

    def process_item(self, item: Any) -> Any:
        if isinstance(item, dict):
            payload = dict(item)
            payload.setdefault("processed_at", datetime.now(timezone.utc).isoformat())
            return payload
        return item
