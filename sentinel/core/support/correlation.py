"""Correlation ID propagation across Sentinel layers."""

from __future__ import annotations

import contextvars
import logging
import uuid

_CORR = contextvars.ContextVar[str]("sentinel_correlation_id", default="")


def get_correlation_id() -> str:
    return _CORR.get()


def set_correlation_id(value: str) -> None:
    _CORR.set(value)


def new_correlation_id() -> str:
    cid = uuid.uuid4().hex
    _CORR.set(cid)
    return cid


def correlation_id(value: str | None = None) -> str:
    """Return the current correlation ID, optionally seeding it."""
    if value:
        _CORR.set(value)
        return value
    current = _CORR.get()
    if not current:
        return new_correlation_id()
    return current


class CorrelationFilter(logging.Filter):
    """Attach correlation_id and build_id to every log record."""

    def __init__(self, build_id: str = "") -> None:
        super().__init__()
        self.build_id = build_id

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = get_correlation_id()
        record.build_id = self.build_id
        return True
