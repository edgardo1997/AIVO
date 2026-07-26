"""In-memory metrics for shadow decision comparisons."""

from dataclasses import dataclass

from .decision_comparison import (
    ShadowDecisionComparison,
    ShadowDecisionComparisonStatus,
)


@dataclass
class ShadowDecisionMetrics:
    total_comparisons: int = 0
    matches: int = 0
    divergences: int = 0
    conversion_errors: int = 0
    missing_contracts: int = 0

    def record_match(self) -> None:
        self.total_comparisons += 1
        self.matches += 1

    def record_divergence(self) -> None:
        self.total_comparisons += 1
        self.divergences += 1

    def record_error(self, *, missing_contract: bool = False) -> None:
        self.total_comparisons += 1
        self.conversion_errors += 1
        if missing_contract:
            self.missing_contracts += 1

    def record(self, comparison: ShadowDecisionComparison) -> None:
        if comparison.status is ShadowDecisionComparisonStatus.MATCH:
            self.record_match()
        elif comparison.status is ShadowDecisionComparisonStatus.DIVERGENCE:
            self.record_divergence()
        else:
            self.record_error()
