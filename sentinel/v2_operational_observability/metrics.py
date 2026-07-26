"""Aggregate-only operational metrics."""

from dataclasses import dataclass
from threading import RLock


@dataclass(frozen=True)
class OperationalMetricsSnapshot:
    total_events: int
    error_rate: float
    divergence_rate: float
    rollback_count: int
    canary_duration_seconds: float
    health_changes: int
    incident_count: int


class OperationalMetrics:
    def __init__(self) -> None:
        self._lock = RLock()
        self._events = 0
        self._errors = 0
        self._divergences = 0
        self._rollbacks = 0
        self._duration = 0.0
        self._health_changes = 0
        self._incidents = 0

    def record(
        self,
        *,
        events: int,
        errors: int,
        divergences: int,
        rollbacks: int,
        canary_duration_seconds: float,
        health_changed: bool,
        incident: bool,
    ) -> None:
        with self._lock:
            self._events += max(0, events)
            self._errors += max(0, errors)
            self._divergences += max(0, divergences)
            self._rollbacks += max(0, rollbacks)
            self._duration = max(
                self._duration,
                max(0.0, canary_duration_seconds),
            )
            self._health_changes += int(health_changed)
            self._incidents += int(incident)

    def snapshot(self) -> OperationalMetricsSnapshot:
        with self._lock:
            denominator = max(self._events, 1)
            return OperationalMetricsSnapshot(
                total_events=self._events,
                error_rate=self._errors / denominator,
                divergence_rate=self._divergences / denominator,
                rollback_count=self._rollbacks,
                canary_duration_seconds=self._duration,
                health_changes=self._health_changes,
                incident_count=self._incidents,
            )
