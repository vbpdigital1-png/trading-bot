"""Structured JSON-lines logging to logs/YYYY-MM-DD.jsonl (UTC dates).

Usage:
    log = get_logger("data")
    log_event(log, "gap_found", pair="EUR_USD", start="...", missing=5)
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_ROOT = "fxbot"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "module": record.name.removeprefix(f"{_ROOT}."),
            "event": getattr(record, "event", None) or record.getMessage(),
        }
        entry.update(getattr(record, "fields", {}))
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


class DailyJsonlHandler(logging.Handler):
    """Appends each record to the file for the record's UTC date."""

    def __init__(self, directory: str | Path):
        super().__init__()
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.setFormatter(JsonFormatter())

    def path_for(self, record: logging.LogRecord) -> Path:
        day = datetime.fromtimestamp(record.created, UTC).strftime("%Y-%m-%d")
        return self.directory / f"{day}.jsonl"

    def emit(self, record: logging.LogRecord) -> None:
        try:
            line = self.format(record)
            with open(self.path_for(record), "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            self.handleError(record)


def setup_logging(directory: str | Path = "logs", level: str = "INFO", console: bool = True) -> None:
    root = logging.getLogger(_ROOT)
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(DailyJsonlHandler(directory))
    if console:
        stream = logging.StreamHandler()
        stream.setFormatter(JsonFormatter())
        root.addHandler(stream)
    root.propagate = False


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"{_ROOT}.{name}")


def log_event(logger: logging.Logger, event: str, level: int = logging.INFO, **fields: Any) -> None:
    logger.log(level, event, extra={"event": event, "fields": fields})
