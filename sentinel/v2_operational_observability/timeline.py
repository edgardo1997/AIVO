"""Bounded operational timeline using the central audit contract."""

import re

from sentinel.contract_adapters import adapt_audit
from sentinel.contracts import AuditEventV1

_EVENT_TYPES = {
    "activation_attempt",
    "canary_started",
    "health_warning",
    "divergence_detected",
    "rollback_triggered",
    "recovery_completed",
}


OperationalTimelineEvent = AuditEventV1


class OperationalTimeline:
    def __init__(self, capacity: int = 1000) -> None:
        self._capacity = max(1, capacity)
        self._events: list[OperationalTimelineEvent] = []

    def append(
        self,
        *,
        event_type: str,
        correlation_hash: str,
        sanitized_result: str,
    ) -> None:
        if event_type not in _EVENT_TYPES:
            raise ValueError("unsupported timeline event")
        if not re.fullmatch(r"[a-f0-9]{64}", correlation_hash):
            raise ValueError("invalid correlation hash")
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", sanitized_result):
            raise ValueError("timeline result must be sanitized")
        adapted = adapt_audit(
            (event_type, sanitized_result),
            correlation_id=correlation_hash,
            event_type=event_type,
            result=sanitized_result,
        )
        self._events.append(adapted.contract)
        del self._events[: -self._capacity]

    def snapshot(self) -> tuple[OperationalTimelineEvent, ...]:
        return tuple(self._events)
