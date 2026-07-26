"""Bounded gateway audit using the central audit contract."""

from sentinel.contract_adapters import adapt_audit
from sentinel.contracts import AuditEventV1

_ALLOWED_EVENTS = {
    "gateway_evaluated",
    "v2_candidate_selected",
    "legacy_selected",
    "selection_blocked",
    "fallback_required",
}


GatewayAuditEvent = AuditEventV1


class ActivationGatewayAudit:
    def __init__(self, capacity: int = 1000) -> None:
        self._capacity = max(1, capacity)
        self._events: list[GatewayAuditEvent] = []

    def record(self, event: str, result: str) -> None:
        if event not in _ALLOWED_EVENTS:
            raise ValueError("unsupported gateway audit event")
        correlation_id = f"gateway-audit:{len(self._events) + 1}"
        adapted = adapt_audit(
            (event, result),
            correlation_id=correlation_id,
            event_type=event,
            result=result,
        )
        self._events.append(adapted.contract)
        del self._events[: -self._capacity]

    def snapshot(self) -> tuple[GatewayAuditEvent, ...]:
        return tuple(self._events)
