"""Sanitized in-memory audit for authorization canary events."""

from enum import Enum
from threading import RLock

from sentinel.contract_adapters import adapt_audit
from sentinel.contracts import AuditEventV1


class CanaryAuditEvent(str, Enum):
    GRANT_CREATED = "grant_created"
    GRANT_VALIDATION_FAILED = "grant_validation_failed"
    GRANT_CONSUMED_SIMULATION = "grant_consumed_simulation"


CanaryAuditRecord = AuditEventV1


class CanaryAuditLog:
    """Store event categories only, never identities or grant payloads."""

    def __init__(self) -> None:
        self._records: list[CanaryAuditRecord] = []
        self._lock = RLock()

    def record(
        self,
        event: CanaryAuditEvent,
        *,
        reason_code: str | None = None,
    ) -> None:
        with self._lock:
            self._records.append(
                adapt_audit(
                    (event.value, reason_code),
                    correlation_id=f"authorization-audit:{len(self._records) + 1}",
                    event_type=event.value,
                    result=reason_code or "RECORDED",
                    issuer_id="authorization_canary",
                ).contract
            )

    def records(self) -> tuple[CanaryAuditRecord, ...]:
        with self._lock:
            return tuple(self._records)
