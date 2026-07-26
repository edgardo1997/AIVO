"""Trend detection over ordered aggregate windows."""

from enum import Enum

from .aggregation import DecisionAggregateSnapshot


class TrendStatus(str, Enum):
    STABLE = "STABLE"
    IMPROVING = "IMPROVING"
    DEGRADING = "DEGRADING"
    UNSTABLE = "UNSTABLE"


class DecisionTrendAnalyzer:
    def analyze(
        self,
        snapshots: tuple[DecisionAggregateSnapshot, ...],
    ) -> TrendStatus:
        if len(snapshots) < 2:
            return TrendStatus.STABLE
        rates = [item.match_rate for item in snapshots]
        deltas = [right - left for left, right in zip(rates, rates[1:])]
        if any(item.critical_divergences > 0 or item.error_rate > 0.2 for item in snapshots):
            return TrendStatus.UNSTABLE
        if all(delta > 0.01 for delta in deltas):
            return TrendStatus.IMPROVING
        if all(delta < -0.01 for delta in deltas):
            return TrendStatus.DEGRADING
        if max(rates) - min(rates) > 0.2:
            return TrendStatus.UNSTABLE
        return TrendStatus.STABLE
