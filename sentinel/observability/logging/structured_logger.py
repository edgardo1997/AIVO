"""Structured Logging — JSON-formatted log events with trace context."""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import json
import logging
import sys


@dataclass
class LogEvent:
    timestamp: str = ""
    level: str = "INFO"
    event: str = ""
    message: str = ""
    component: str = ""
    trace_id: str = ""
    span_id: str = ""
    duration_ms: float = 0.0
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "timestamp": self.timestamp or datetime.now(timezone.utc).isoformat(),
            "level": self.level,
            "event": self.event,
            "message": self.message,
        }
        if self.component:
            result["component"] = self.component
        if self.trace_id:
            result["trace_id"] = self.trace_id
        if self.span_id:
            result["span_id"] = self.span_id
        if self.duration_ms:
            result["duration_ms"] = round(self.duration_ms, 1)
        if self.extra:
            result.update(self.extra)
        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)


class StructuredLogger:
    """Wraps Python's logging with structured JSON output and trace context."""

    def __init__(self, name: str = "sentinel", level: str = "INFO", trace_manager: Any = None):
        self._logger = logging.getLogger(name)
        self._logger.setLevel(getattr(logging, level.upper(), logging.INFO))
        self._trace_manager = trace_manager

        if not self._logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(logging.Formatter("%(message)s"))
            self._logger.addHandler(handler)

    def _trace_context(self) -> Dict[str, str]:
        if self._trace_manager is None:
            return {}
        return {
            "trace_id": self._trace_manager.current_trace_id or "",
            "span_id": self._trace_manager.current_span_id or "",
        }

    def _log(self, level: str, event: str, message: str = "", component: str = "", duration_ms: float = 0.0, **extra: Any) -> None:
        ctx = self._trace_context()
        log_event = LogEvent(
            level=level,
            event=event,
            message=message,
            component=component,
            trace_id=ctx.get("trace_id", ""),
            span_id=ctx.get("span_id", ""),
            duration_ms=duration_ms,
            extra=extra,
        )
        log_level = getattr(logging, level.upper(), logging.INFO)
        self._logger.log(log_level, log_event.to_json())

    def info(self, event: str, message: str = "", component: str = "", duration_ms: float = 0.0, **extra: Any) -> None:
        self._log("INFO", event, message, component, duration_ms, **extra)

    def warning(self, event: str, message: str = "", component: str = "", duration_ms: float = 0.0, **extra: Any) -> None:
        self._log("WARNING", event, message, component, duration_ms, **extra)

    def error(self, event: str, message: str = "", component: str = "", duration_ms: float = 0.0, **extra: Any) -> None:
        self._log("ERROR", event, message, component, duration_ms, **extra)

    def debug(self, event: str, message: str = "", component: str = "", duration_ms: float = 0.0, **extra: Any) -> None:
        self._log("DEBUG", event, message, component, duration_ms, **extra)
