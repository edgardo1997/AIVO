"""Passive aggregate shadow metrics."""

from dataclasses import dataclass

from sentinel.contracts import DecisionResultV1

from .equivalence import EquivalenceLevel


class ShadowDecisionMetricSnapshotV1(DecisionResultV1):
    comparisons: int
    matches: int
    partial_matches: int
    divergences: int
    critical_divergences: int


@dataclass
class ShadowDecisionMetrics:
    comparisons: int = 0
    matches: int = 0
    partial_matches: int = 0
    divergences: int = 0
    critical_divergences: int = 0

    def record(self, classification: EquivalenceLevel) -> None:
        self.comparisons += 1
        self.matches += int(classification is EquivalenceLevel.MATCH)
        self.partial_matches += int(classification is EquivalenceLevel.PARTIAL_MATCH)
        self.divergences += int(classification is EquivalenceLevel.DIVERGENCE)
        self.critical_divergences += int(classification is EquivalenceLevel.CRITICAL_DIVERGENCE)

    def snapshot(self) -> ShadowDecisionMetricSnapshotV1:
        return ShadowDecisionMetricSnapshotV1(**vars(self))
