"""Bounded transition audit using the central audit contract."""

import re

from sentinel.contract_adapters import adapt_audit
from sentinel.contracts import AuditEventV1

AuthorityAuditEvent = AuditEventV1


class AuthorityAuditLog:
    def __init__(self, capacity: int = 1000) -> None:
        self._capacity = max(1, capacity)
        self._events: list[AuthorityAuditEvent] = []

    def record(
        self,
        *,
        transition_type: str,
        state: str,
        result: str,
    ) -> None:
        for value in (transition_type, state, result):
            if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", value):
                raise ValueError("audit values must be sanitized codes")
        correlation_id = f"authority-audit:{len(self._events) + 1}"
        adapted = adapt_audit(
            (transition_type, state, result),
            correlation_id=correlation_id,
            event_type=transition_type,
            result=f"{state}_{result}",
        )
        self._events.append(adapted.contract)
        del self._events[: -self._capacity]

    def snapshot(self) -> tuple[AuthorityAuditEvent, ...]:
        return tuple(self._events)
