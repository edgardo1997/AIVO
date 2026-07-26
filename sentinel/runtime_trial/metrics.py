"""Aggregate metrics with no scenario or payload retention."""

from dataclasses import dataclass
from threading import RLock

from .comparison import RuntimeTrialComparisonStatus


@dataclass(frozen=True)
class RuntimeTrialMetricsSnapshot:
    scenarios_run: int
    successes: int
    failures: int
    divergences: int
    average_latency_ms: float
    maximum_latency_ms: float
    conversions: int


class RuntimeTrialMetrics:
    def __init__(self) -> None:
        self._lock = RLock()
        self._count = 0
        self._successes = 0
        self._failures = 0
        self._divergences = 0
        self._latency_total = 0.0
        self._latency_max = 0.0
        self._conversions = 0

    def record(
        self,
        *,
        succeeded: bool,
        comparison: RuntimeTrialComparisonStatus,
        latency_ms: float,
        conversions: int,
    ) -> None:
        latency = max(0.0, float(latency_ms))
        with self._lock:
            self._count += 1
            self._successes += int(succeeded)
            self._failures += int(not succeeded)
            self._divergences += int(comparison is not RuntimeTrialComparisonStatus.MATCH)
            self._latency_total += latency
            self._latency_max = max(self._latency_max, latency)
            self._conversions += max(0, int(conversions))

    def snapshot(self) -> RuntimeTrialMetricsSnapshot:
        with self._lock:
            return RuntimeTrialMetricsSnapshot(
                scenarios_run=self._count,
                successes=self._successes,
                failures=self._failures,
                divergences=self._divergences,
                average_latency_ms=self._latency_total / max(self._count, 1),
                maximum_latency_ms=self._latency_max,
                conversions=self._conversions,
            )
