"""Bounded activation audit using the central audit contract."""

import re

from sentinel.contract_adapters import adapt_audit
from sentinel.contracts import AuditEventV1

_EVENTS = {
    "activation_started",
    "legacy_selected",
    "v2_selected",
    "rollback_triggered",
    "activation_paused",
}


ActivationAuditEvent = AuditEventV1


class ActivationAudit:
    def __init__(self, capacity: int = 1000) -> None:
        self._capacity = max(1, capacity)
        self._events: list[ActivationAuditEvent] = []

    def record(self, event: str, result: str) -> None:
        if event not in _EVENTS:
            raise ValueError("unsupported activation event")
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", result):
            raise ValueError("activation audit result must be sanitized")
        correlation_id = f"activation-audit:{len(self._events) + 1}"
        adapted = adapt_audit(
            (event, result),
            correlation_id=correlation_id,
            event_type=event,
            result=result,
        )
        self._events.append(adapted.contract)
        del self._events[: -self._capacity]

    def snapshot(self) -> tuple[ActivationAuditEvent, ...]:
        return tuple(self._events)
