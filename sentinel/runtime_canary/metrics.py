"""Aggregate-only metrics for runtime canary observations."""

from dataclasses import dataclass
from threading import RLock

from .diagnostics import RuntimeCanaryResult


@dataclass(frozen=True)
class RuntimeCanaryMetricsSnapshot:
    planner_matches: int
    planner_mismatches: int
    discovery_matches: int
    policy_matches: int
    authorization_matches: int
    identity_mismatches: int
    context_mismatches: int
    schema_gaps: int
    validation_failures: int
    average_runtime_ms: float
    maximum_runtime_ms: float


class RuntimeCanaryMetrics:
    """Store counters and durations only, never event payloads."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._counts = {
            "planner_matches": 0,
            "planner_mismatches": 0,
            "discovery_matches": 0,
            "policy_matches": 0,
            "authorization_matches": 0,
            "identity_mismatches": 0,
            "context_mismatches": 0,
            "schema_gaps": 0,
            "validation_failures": 0,
        }
        self._runtime_total_ms = 0.0
        self._runtime_max_ms = 0.0
        self._observations = 0

    def record(self, result: RuntimeCanaryResult) -> None:
        comparison = result.comparison_result
        warnings = set(result.warnings)
        with self._lock:
            if comparison.get("planner_match", False):
                self._counts["planner_matches"] += 1
            else:
                self._counts["planner_mismatches"] += 1
            self._counts["discovery_matches"] += int(comparison.get("discovery_match", False))
            self._counts["policy_matches"] += int(comparison.get("policy_match", False))
            self._counts["authorization_matches"] += int(comparison.get("authorization_match", False))
            self._counts["identity_mismatches"] += any("identity" in item for item in warnings)
            self._counts["context_mismatches"] += any("context" in item for item in warnings)
            self._counts["schema_gaps"] += len(result.schema_gaps)
            self._counts["validation_failures"] += len(result.validation_errors)
            self._observations += 1
            self._runtime_total_ms += result.execution_time_ms
            self._runtime_max_ms = max(
                self._runtime_max_ms,
                result.execution_time_ms,
            )

    def snapshot(self) -> RuntimeCanaryMetricsSnapshot:
        with self._lock:
            average = self._runtime_total_ms / self._observations if self._observations else 0.0
            return RuntimeCanaryMetricsSnapshot(
                **self._counts,
                average_runtime_ms=average,
                maximum_runtime_ms=self._runtime_max_ms,
            )
