"""Aggregate-only metrics for policy shadow comparisons."""

from dataclasses import dataclass
from threading import RLock

from .comparison import PolicyShadowComparison


@dataclass(frozen=True)
class PolicyShadowMetricsSnapshot:
    policy_match: int
    policy_difference: int
    missing_context: int
    missing_identity: int
    missing_policy_version: int


class PolicyShadowMetrics:
    def __init__(self) -> None:
        self._lock = RLock()
        self._counts = {
            "policy_match": 0,
            "policy_difference": 0,
            "missing_context": 0,
            "missing_identity": 0,
            "missing_policy_version": 0,
        }

    def record(self, comparison: PolicyShadowComparison) -> None:
        tokens = set(comparison.differences) | set(comparison.warnings)
        with self._lock:
            self._counts["policy_match" if comparison.match else "policy_difference"] += 1
            self._counts["missing_context"] += any("missing_context" in value for value in tokens)
            self._counts["missing_identity"] += any("missing_identity" in value for value in tokens)
            self._counts["missing_policy_version"] += any("policy_version" in value for value in tokens)

    def snapshot(self) -> PolicyShadowMetricsSnapshot:
        with self._lock:
            return PolicyShadowMetricsSnapshot(**self._counts)
