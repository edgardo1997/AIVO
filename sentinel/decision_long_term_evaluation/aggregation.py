"""Immutable aggregate snapshot without individual decisions."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DecisionAggregateSnapshot:
    total_decisions: int
    matches: int
    divergences: int
    security_improvements: int
    critical_divergences: int
    errors: int
    average_latency_ms: float
    maximum_latency_ms: float
    lost_records: int

    @property
    def match_rate(self) -> float:
        return self.matches / max(self.total_decisions, 1)

    @property
    def divergence_rate(self) -> float:
        return self.divergences / max(self.total_decisions, 1)

    @property
    def error_rate(self) -> float:
        return self.errors / max(self.total_decisions, 1)
