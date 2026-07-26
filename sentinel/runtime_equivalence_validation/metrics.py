"""Aggregate-only equivalence counters."""

from dataclasses import dataclass
from threading import RLock

from .equivalence import EquivalenceClassification


@dataclass(frozen=True)
class EquivalenceMetricsSnapshot:
    comparisons: int
    matches: int
    divergences: int
    errors: int
    average_latency_ms: float
    maximum_latency_ms: float


class EquivalenceMetrics:
    def __init__(self) -> None:
        self._lock = RLock()
        self._comparisons = 0
        self._matches = 0
        self._divergences = 0
        self._errors = 0
        self._latency_total = 0.0
        self._latency_max = 0.0

    def record(
        self,
        *,
        classification: EquivalenceClassification,
        latency_ms: float,
        error: bool = False,
    ) -> None:
        latency = max(0.0, float(latency_ms))
        with self._lock:
            self._comparisons += 1
            self._matches += int(classification is EquivalenceClassification.EQUIVALENT)
            self._divergences += int(classification is not EquivalenceClassification.EQUIVALENT)
            self._errors += int(error)
            self._latency_total += latency
            self._latency_max = max(self._latency_max, latency)

    def snapshot(self) -> EquivalenceMetricsSnapshot:
        with self._lock:
            return EquivalenceMetricsSnapshot(
                comparisons=self._comparisons,
                matches=self._matches,
                divergences=self._divergences,
                errors=self._errors,
                average_latency_ms=(self._latency_total / max(self._comparisons, 1)),
                maximum_latency_ms=self._latency_max,
            )
