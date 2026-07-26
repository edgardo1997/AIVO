"""Thread-safe aggregate-only metrics for a canary session."""

from dataclasses import dataclass
from threading import RLock


@dataclass(frozen=True)
class CanaryMetricsSnapshot:
    processed_events: int
    errors: int
    average_latency_ms: float
    maximum_latency_ms: float
    divergences: int
    matches: int
    successful_conversions: int
    failed_conversions: int


class CanaryEnvironmentMetrics:
    def __init__(self) -> None:
        self._lock = RLock()
        self._processed = 0
        self._errors = 0
        self._latency_total = 0.0
        self._latency_max = 0.0
        self._divergences = 0
        self._matches = 0
        self._successful_conversions = 0
        self._failed_conversions = 0

    def record(
        self,
        *,
        latency_ms: float,
        matched: bool,
        conversion_succeeded: bool,
        error: bool = False,
    ) -> None:
        latency = max(0.0, float(latency_ms))
        with self._lock:
            self._processed += 1
            self._errors += int(error)
            self._latency_total += latency
            self._latency_max = max(self._latency_max, latency)
            self._matches += int(matched)
            self._divergences += int(not matched)
            self._successful_conversions += int(conversion_succeeded)
            self._failed_conversions += int(not conversion_succeeded)

    def snapshot(self) -> CanaryMetricsSnapshot:
        with self._lock:
            denominator = max(self._processed, 1)
            return CanaryMetricsSnapshot(
                processed_events=self._processed,
                errors=self._errors,
                average_latency_ms=self._latency_total / denominator,
                maximum_latency_ms=self._latency_max,
                divergences=self._divergences,
                matches=self._matches,
                successful_conversions=self._successful_conversions,
                failed_conversions=self._failed_conversions,
            )
