"""Persistence pipeline for storing processed items."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .base_pipeline import BasePipeline


class DataSaverPipeline(BasePipeline):
    """Append each processed item to a JSON lines file."""

    def __init__(self, output_dir: Path, *, filename: str | None = None) -> None:
        self._output_dir = output_dir
        self._filename = filename or f"items_{datetime.utcnow().strftime('%Y%m%d')}.jsonl"
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._path = self._output_dir / self._filename

    def process_item(self, item: Any) -> Any:
        payload = item
        if isinstance(payload, set):
            payload = sorted(payload)
        self._append_json_line(payload)
        return item

    def _append_json_line(self, item: Any) -> None:
        with self._path.open("a", encoding="utf-8") as fp:
            json.dump(item, fp, ensure_ascii=False)
            fp.write("\n")
