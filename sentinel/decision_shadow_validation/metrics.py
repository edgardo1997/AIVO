"""Aggregate-only metrics for decision validation."""

from dataclasses import dataclass
from threading import RLock

from .classification import DecisionClassification


@dataclass(frozen=True)
class DecisionShadowMetricsSnapshot:
    decisions_evaluated: int
    matches: int
    divergences: int
    security_improvements: int
    errors: int
    average_latency_ms: float
    maximum_latency_ms: float


class DecisionShadowMetrics:
    def __init__(self) -> None:
        self._lock = RLock()
        self._evaluated = 0
        self._matches = 0
        self._divergences = 0
        self._security_improvements = 0
        self._errors = 0
        self._latency_total = 0.0
        self._latency_max = 0.0

    def record(
        self,
        *,
        classification: DecisionClassification,
        latency_ms: float,
        error: bool = False,
    ) -> None:
        latency = max(0.0, float(latency_ms))
        with self._lock:
            self._evaluated += 1
            self._matches += int(classification is DecisionClassification.EXPECTED_MATCH)
            self._divergences += int(classification is not DecisionClassification.EXPECTED_MATCH)
            self._security_improvements += int(classification is DecisionClassification.SECURITY_IMPROVEMENT)
            self._errors += int(error)
            self._latency_total += latency
            self._latency_max = max(self._latency_max, latency)

    def snapshot(self) -> DecisionShadowMetricsSnapshot:
        with self._lock:
            return DecisionShadowMetricsSnapshot(
                decisions_evaluated=self._evaluated,
                matches=self._matches,
                divergences=self._divergences,
                security_improvements=self._security_improvements,
                errors=self._errors,
                average_latency_ms=(self._latency_total / max(self._evaluated, 1)),
                maximum_latency_ms=self._latency_max,
            )
