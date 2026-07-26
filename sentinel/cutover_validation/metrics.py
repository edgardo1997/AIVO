"""Historical aggregate metrics for validation runs."""

from dataclasses import dataclass
from threading import RLock


@dataclass(frozen=True)
class CutoverHistoricalMetricsSnapshot:
    total_events: int
    matched_decisions: int
    divergent_decisions: int
    policy_match_rate: float
    discovery_match_rate: float
    authorization_match_rate: float
    average_latency: float
    max_latency: float
    validation_runs: int
    blocked_runs: int


class CutoverHistoricalMetrics:
    """Retain aggregate counters only; no event or identity records."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._totals = {
            "total_events": 0,
            "matched_decisions": 0,
            "divergent_decisions": 0,
            "policy_match_sum": 0.0,
            "discovery_match_sum": 0.0,
            "authorization_match_sum": 0.0,
            "latency_total": 0.0,
            "max_latency": 0.0,
            "validation_runs": 0,
            "blocked_runs": 0,
        }

    def record(
        self,
        metrics: dict[str, int | float],
        *,
        blocked: bool,
    ) -> None:
        allowed = {
            "total_events",
            "matched_decisions",
            "divergent_decisions",
            "policy_match_rate",
            "discovery_match_rate",
            "authorization_match_rate",
            "average_latency",
            "max_latency",
        }
        if set(metrics) - allowed:
            raise ValueError("historical metrics contain unsupported fields")
        with self._lock:
            self._totals["total_events"] += int(metrics.get("total_events", 0))
            self._totals["matched_decisions"] += int(metrics.get("matched_decisions", 0))
            self._totals["divergent_decisions"] += int(metrics.get("divergent_decisions", 0))
            self._totals["policy_match_sum"] += float(metrics.get("policy_match_rate", 0.0))
            self._totals["discovery_match_sum"] += float(metrics.get("discovery_match_rate", 0.0))
            self._totals["authorization_match_sum"] += float(metrics.get("authorization_match_rate", 0.0))
            self._totals["latency_total"] += float(metrics.get("average_latency", 0.0))
            self._totals["max_latency"] = max(
                self._totals["max_latency"],
                float(metrics.get("max_latency", 0.0)),
            )
            self._totals["validation_runs"] += 1
            self._totals["blocked_runs"] += int(blocked)

    def snapshot(self) -> CutoverHistoricalMetricsSnapshot:
        with self._lock:
            runs = max(int(self._totals["validation_runs"]), 1)
            return CutoverHistoricalMetricsSnapshot(
                total_events=int(self._totals["total_events"]),
                matched_decisions=int(self._totals["matched_decisions"]),
                divergent_decisions=int(self._totals["divergent_decisions"]),
                policy_match_rate=(self._totals["policy_match_sum"] / runs),
                discovery_match_rate=(self._totals["discovery_match_sum"] / runs),
                authorization_match_rate=(self._totals["authorization_match_sum"] / runs),
                average_latency=self._totals["latency_total"] / runs,
                max_latency=self._totals["max_latency"],
                validation_runs=int(self._totals["validation_runs"]),
                blocked_runs=int(self._totals["blocked_runs"]),
            )
