"""Logging helpers."""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

_RESERVED_ATTRS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "message",
    "asctime",
}


class JsonFormatter(logging.Formatter):
    """Render log records as compact JSON."""

    default_time_format = "%Y-%m-%dT%H:%M:%S"
    default_msec_format = "%s.%03dZ"

    def format(self, record: logging.LogRecord) -> str:  # pragma: no cover - exercised indirectly
        message = record.getMessage()
        data: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.default_time_format),
            "level": record.levelname,
            "logger": record.name,
            "message": message,
        }

        extras = {
            key: value for key, value in record.__dict__.items() if key not in _RESERVED_ATTRS
        }
        if extras:
            data.update(extras)

        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)

        return json.dumps(data, ensure_ascii=False)


def configure_logging(
    *,
    level: int = logging.INFO,
    structured: bool | None = None,
) -> None:
    """Configure root logging with optional JSON output."""

    root = logging.getLogger()
    root.setLevel(level)

    if root.handlers:
        if structured is None:
            return
        formatter: logging.Formatter
        if structured:
            formatter = JsonFormatter()
        else:
            formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        for handler in root.handlers:
            handler.setFormatter(formatter)
        return

    handler = logging.StreamHandler(sys.stdout)
    if structured:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


__all__ = ["configure_logging", "get_logger", "JsonFormatter"]
