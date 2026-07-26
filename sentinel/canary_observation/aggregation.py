"""Bounded in-memory aggregation feeding sanitized local storage."""

from collections import deque
from datetime import timezone

from sentinel.runtime_canary import RuntimeCanaryResult

from .diagnostics import CanaryObservationDiagnostic
from .storage import CanaryAggregateStorage


class CanaryMetricsAggregator:
    def __init__(
        self,
        storage: CanaryAggregateStorage,
        *,
        max_recent: int = 256,
    ) -> None:
        if max_recent < 1:
            raise ValueError("max_recent must be positive")
        self.storage = storage
        self._recent: deque[CanaryObservationDiagnostic] = deque(maxlen=max_recent)
        self.events_ignored = 0
        self.events_dropped = 0

    @property
    def recent_count(self) -> int:
        return len(self._recent)

    @property
    def capacity(self) -> int:
        return self._recent.maxlen or 0

    def recent(self) -> tuple[CanaryObservationDiagnostic, ...]:
        return tuple(self._recent)

    def record(
        self,
        diagnostic: CanaryObservationDiagnostic,
        result: RuntimeCanaryResult,
    ) -> None:
        if len(self._recent) == self.capacity:
            self.events_dropped += 1
        self._recent.append(diagnostic)
        comparison = result.comparison_result
        day = diagnostic.timestamp.astimezone(timezone.utc).date().isoformat()
        self.storage.update(
            day,
            {
                "events_total": 1,
                "schema_errors": len(result.schema_gaps),
                "differences": len(comparison.get("differences", ())),
                "conversion_failures": sum("conversion" in item for item in result.validation_errors),
                "validation_failures": len(result.validation_errors),
                "planner_matches": int(comparison.get("planner_match", False)),
                "planner_total": 1,
                "policy_matches": int(comparison.get("policy_match", False)),
                "policy_total": 1,
                "authorization_matches": int(comparison.get("authorization_match", False)),
                "authorization_total": 1,
                "latency_total_ms": diagnostic.latency_ms,
                "maximum_latency_ms": diagnostic.latency_ms,
                "errors": int(diagnostic.status == "ERROR"),
            },
        )

    def record_ignored(self, *, day: str) -> None:
        self.events_ignored += 1
        self.storage.update(day, {"events_ignored": 1})

    def record_failure(
        self,
        diagnostic: CanaryObservationDiagnostic,
    ) -> None:
        if len(self._recent) == self.capacity:
            self.events_dropped += 1
        self._recent.append(diagnostic)
        day = diagnostic.timestamp.astimezone(timezone.utc).date().isoformat()
        self.storage.update(
            day,
            {
                "events_total": 1,
                "validation_failures": 1,
                "errors": 1,
                "latency_total_ms": diagnostic.latency_ms,
                "maximum_latency_ms": diagnostic.latency_ms,
            },
        )
