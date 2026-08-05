"""Structured logging with correlation_id and build_id."""

from __future__ import annotations

import json
import logging
import logging.handlers
from pathlib import Path
from typing import Any, Optional

from .correlation import CorrelationFilter


def setup_structured_logging(
    build_id: str = "",
    log_dir: Optional[Path] = None,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 5,
    level: int = logging.INFO,
) -> None:
    """Configure root logging to emit JSON with correlation_id and build_id."""
    if log_dir is None:
        log_dir = Path.home() / ".sentinel" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "sentinel.jsonl"

    handler = logging.handlers.RotatingFileHandler(
        str(log_file),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.addFilter(CorrelationFilter(build_id=build_id))
    handler.setFormatter(logging.Formatter("%(message)s"))

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [handler, console]


def log_structured(
    level: str,
    component: str,
    event: str,
    message: str,
    build_id: str = "",
    error_code: Optional[str] = None,
    operation_state: Optional[str] = None,
    **kwargs: Any,
) -> None:
    """Emit a single structured JSON log record."""
    from .correlation import get_correlation_id

    record = {
        "timestamp": _utc_now(),
        "level": level.upper(),
        "component": component,
        "event": event,
        "message": message,
        "correlation_id": get_correlation_id(),
        "build_id": build_id,
    }
    if error_code:
        record["error_code"] = error_code
    if operation_state:
        record["operation_state"] = operation_state
    record.update(kwargs)
    logger = logging.getLogger(component)
    if level.upper() == "DEBUG":
        logger.debug(json.dumps(record, ensure_ascii=False))
    elif level.upper() == "INFO":
        logger.info(json.dumps(record, ensure_ascii=False))
    elif level.upper() == "WARNING":
        logger.warning(json.dumps(record, ensure_ascii=False))
    elif level.upper() == "ERROR":
        logger.error(json.dumps(record, ensure_ascii=False))
    elif level.upper() == "CRITICAL":
        logger.critical(json.dumps(record, ensure_ascii=False))


def _utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
