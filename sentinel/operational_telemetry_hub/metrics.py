"""Sanitized aggregate metrics shared by telemetry consumers."""

from dataclasses import dataclass
from threading import RLock

from sentinel.contracts import DecisionResultV1, EvidenceIntegrityStatusV1

from .events import OperationalEventV1


class OperationalMetricSnapshotV1(DecisionResultV1):
    decisions: int
    divergences: int
    errors: int
    rollbacks: int
    health_transitions: int
    evidence_verified: int
    evidence_rejected: int
    canary_observations: int


@dataclass
class _MutableCounters:
    decisions: int = 0
    divergences: int = 0
    errors: int = 0
    rollbacks: int = 0
    health_transitions: int = 0
    evidence_verified: int = 0
    evidence_rejected: int = 0
    canary_observations: int = 0


class OperationalMetricAggregator:
    def __init__(self) -> None:
        self._values = _MutableCounters()
        self._last_health: str | None = None
        self._lock = RLock()

    def record(self, event: OperationalEventV1) -> None:
        with self._lock:
            event_type = event.event_type
            self._values.decisions += int("DECISION" in event_type)
            self._values.divergences += int("DIVERGENCE" in event_type)
            self._values.errors += int("ERROR" in event_type or event.decision_state == "FAILED")
            self._values.rollbacks += int("ROLLBACK" in event_type)
            self._values.canary_observations += int("CANARY" in event_type)
            self._values.evidence_verified += int(event.integrity_status is EvidenceIntegrityStatusV1.VERIFIED)
            self._values.evidence_rejected += int(event.integrity_status is EvidenceIntegrityStatusV1.INVALID)
            if self._last_health is not None and self._last_health != event.health_state.value:
                self._values.health_transitions += 1
            self._last_health = event.health_state.value

    def snapshot(self) -> OperationalMetricSnapshotV1:
        with self._lock:
            return OperationalMetricSnapshotV1(**vars(self._values))
