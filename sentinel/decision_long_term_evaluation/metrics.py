"""Aggregate decision counters for one evaluation window."""

from threading import RLock

from sentinel.decision_shadow_validation.classification import (
    DecisionClassification,
)

from .aggregation import DecisionAggregateSnapshot


class DecisionLongTermMetrics:
    def __init__(self) -> None:
        self._lock = RLock()
        self._total = 0
        self._matches = 0
        self._divergences = 0
        self._improvements = 0
        self._critical = 0
        self._errors = 0
        self._latency_total = 0.0
        self._latency_max = 0.0
        self._lost = 0

    def record(
        self,
        *,
        classification: DecisionClassification,
        latency_ms: float,
        error: bool = False,
    ) -> None:
        latency = max(0.0, float(latency_ms))
        with self._lock:
            self._total += 1
            self._matches += int(classification is DecisionClassification.EXPECTED_MATCH)
            self._divergences += int(classification is not DecisionClassification.EXPECTED_MATCH)
            self._improvements += int(classification is DecisionClassification.SECURITY_IMPROVEMENT)
            self._critical += int(classification is DecisionClassification.CRITICAL_DIVERGENCE)
            self._errors += int(error)
            self._latency_total += latency
            self._latency_max = max(self._latency_max, latency)

    def record_loss(self, count: int = 1) -> None:
        with self._lock:
            self._lost += max(0, int(count))

    def snapshot(self) -> DecisionAggregateSnapshot:
        with self._lock:
            return DecisionAggregateSnapshot(
                total_decisions=self._total,
                matches=self._matches,
                divergences=self._divergences,
                security_improvements=self._improvements,
                critical_divergences=self._critical,
                errors=self._errors,
                average_latency_ms=self._latency_total / max(self._total, 1),
                maximum_latency_ms=self._latency_max,
                lost_records=self._lost,
            )
