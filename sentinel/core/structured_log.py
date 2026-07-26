"""Structured JSON logging for Sentinel.

Replaces plain-text log records with JSON-formatted entries
that include timestamp, level, component, execution context, and
machine-readable metadata.  Complements the ObservabilityService
(event-based traces) with a durable, queryable log stream.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class StructuredFormatter(logging.Formatter):
    """Logging formatter that emits JSON records."""

    def format(self, record: logging.LogRecord) -> str:
        entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0]:
            entry["exception"] = self.formatException(record.exc_info)
        extra = getattr(record, "extra", None)
        if isinstance(extra, dict):
            entry.update(extra)
        return json.dumps(entry, default=str)


def configure_json_logging(logger: logging.Logger, level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(StructuredFormatter())
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(level)


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        configure_json_logging(logger, level)
    return logger
