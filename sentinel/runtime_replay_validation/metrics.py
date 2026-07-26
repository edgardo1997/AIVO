"""Histogram-based aggregate replay metrics."""

from dataclasses import dataclass
from threading import RLock

from .comparison import ReplayComparisonStatus


_LATENCY_BOUNDS = (1.0, 5.0, 10.0, 25.0, 50.0, 100.0, 250.0, 500.0)


@dataclass(frozen=True)
class ReplayMetricsSnapshot:
    processed_events: int
    successful_executions: int
    errors: int
    matches: int
    divergences: int
    regressions: int
    non_deterministic_results: int
    average_latency_ms: float
    maximum_latency_ms: float
    latency_percentiles: dict[str, float]


class ReplayMetrics:
    """Retain counters and histogram buckets, never execution records."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._counts = {
            "processed_events": 0,
            "successful_executions": 0,
            "errors": 0,
            "matches": 0,
            "divergences": 0,
            "regressions": 0,
            "non_deterministic_results": 0,
        }
        self._latency_total = 0.0
        self._latency_max = 0.0
        self._histogram = [0] * (len(_LATENCY_BOUNDS) + 1)

    def record(
        self,
        *,
        comparison: ReplayComparisonStatus,
        has_errors: bool,
        latency_ms: float,
    ) -> None:
        with self._lock:
            self._counts["processed_events"] += 1
            self._counts["successful_executions"] += int(not has_errors)
            self._counts["errors"] += int(has_errors)
            self._counts["matches"] += int(comparison is ReplayComparisonStatus.MATCH)
            self._counts["divergences"] += int(comparison is not ReplayComparisonStatus.MATCH)
            self._counts["regressions"] += int(comparison is ReplayComparisonStatus.REGRESSION)
            self._counts["non_deterministic_results"] += int(comparison is ReplayComparisonStatus.NON_DETERMINISTIC)
            safe_latency = max(float(latency_ms), 0.0)
            self._latency_total += safe_latency
            self._latency_max = max(self._latency_max, safe_latency)
            bucket = next(
                (index for index, bound in enumerate(_LATENCY_BOUNDS) if safe_latency <= bound),
                len(_LATENCY_BOUNDS),
            )
            self._histogram[bucket] += 1

    def snapshot(self) -> ReplayMetricsSnapshot:
        with self._lock:
            count = max(self._counts["processed_events"], 1)
            return ReplayMetricsSnapshot(
                **self._counts,
                average_latency_ms=self._latency_total / count,
                maximum_latency_ms=self._latency_max,
                latency_percentiles={
                    "p50": self._percentile(0.50),
                    "p95": self._percentile(0.95),
                    "p99": self._percentile(0.99),
                },
            )

    def _percentile(self, quantile: float) -> float:
        total = sum(self._histogram)
        if total == 0:
            return 0.0
        target = max(1, int(total * quantile + 0.999999))
        cumulative = 0
        for index, count in enumerate(self._histogram):
            cumulative += count
            if cumulative >= target:
                return _LATENCY_BOUNDS[index] if index < len(_LATENCY_BOUNDS) else self._latency_max
        return self._latency_max
