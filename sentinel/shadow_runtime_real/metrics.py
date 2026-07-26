"""Bounded aggregate metrics for prolonged shadow observation."""

from threading import RLock

from pydantic import Field

from sentinel.contracts import DecisionResultV1

from .models import ShadowComparisonResultV1


class ShadowRuntimeMetricsSnapshotV1(DecisionResultV1):
    observations: int = Field(ge=0)
    completed: int = Field(ge=0)
    failures: int = Field(ge=0)
    divergences: int = Field(ge=0)
    divergent_observations: int = Field(ge=0)
    critical_divergences: int = Field(ge=0)
    information_losses: int = Field(ge=0)
    total_latency_ms: float = Field(ge=0.0)
    average_latency_ms: float = Field(ge=0.0)
    maximum_latency_ms: float = Field(ge=0.0)
    consecutive_failures: int = Field(ge=0)


class ShadowRuntimeMetrics:
    """Counters only; no snapshots, users, prompts or payloads are retained."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._observations = 0
        self._completed = 0
        self._failures = 0
        self._divergences = 0
        self._divergent_observations = 0
        self._critical = 0
        self._losses = 0
        self._total_latency_ms = 0.0
        self._maximum_latency_ms = 0.0
        self._consecutive_failures = 0

    def record(
        self,
        *,
        latency_ms: float,
        comparison: ShadowComparisonResultV1 | None,
        failed: bool,
    ) -> None:
        with self._lock:
            self._observations += 1
            self._total_latency_ms += max(0.0, latency_ms)
            self._maximum_latency_ms = max(
                self._maximum_latency_ms,
                max(0.0, latency_ms),
            )
            if failed:
                self._failures += 1
                self._consecutive_failures += 1
            else:
                self._completed += 1
                self._consecutive_failures = 0
            if comparison is not None:
                self._divergences += len(comparison.divergences)
                self._divergent_observations += int(not comparison.matched)
                self._critical += comparison.critical_count
                self._losses += comparison.information_loss_count

    def snapshot(self) -> ShadowRuntimeMetricsSnapshotV1:
        with self._lock:
            average = self._total_latency_ms / self._observations if self._observations else 0.0
            return ShadowRuntimeMetricsSnapshotV1(
                observations=self._observations,
                completed=self._completed,
                failures=self._failures,
                divergences=self._divergences,
                divergent_observations=self._divergent_observations,
                critical_divergences=self._critical,
                information_losses=self._losses,
                total_latency_ms=self._total_latency_ms,
                average_latency_ms=average,
                maximum_latency_ms=self._maximum_latency_ms,
                consecutive_failures=self._consecutive_failures,
            )

    def stability_payload(self) -> dict[str, dict[str, int | float | bool | dict]]:
        """Expose only aggregates accepted by StabilityValidationEngine."""
        snapshot = self.snapshot()
        return {
            "canary_observation": {
                "total_events": snapshot.observations,
                "processed_events": snapshot.completed,
                "ignored_events": 0,
                "dropped_events": snapshot.failures,
                "average_latency_ms": snapshot.average_latency_ms,
                "max_latency_ms": snapshot.maximum_latency_ms,
                "latency_percentiles": {
                    "p50": snapshot.average_latency_ms,
                    "p95": snapshot.maximum_latency_ms,
                    "p99": snapshot.maximum_latency_ms,
                },
                "memory_start": 0.0,
                "memory_current": 0.0,
                "total_errors": snapshot.failures,
                "consecutive_errors": snapshot.consecutive_failures,
                "observer_stable": snapshot.consecutive_failures < 10,
            },
            "runtime_canary": {
                "comparison_matches": (snapshot.completed - snapshot.divergent_observations),
                "comparison_divergences": snapshot.divergent_observations,
                "conversion_failures": snapshot.failures,
            },
        }
