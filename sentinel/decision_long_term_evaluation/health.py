"""Long-term health evaluation over aggregate evidence."""

from sentinel.contracts import HealthStateV1

from .aggregation import DecisionAggregateSnapshot
from .trend import TrendStatus

DecisionLongTermHealthStatus = HealthStateV1


class DecisionLongTermHealthEvaluator:
    def evaluate(
        self,
        snapshot: DecisionAggregateSnapshot,
        *,
        trend: TrendStatus,
        minimum_volume: int = 100,
    ) -> DecisionLongTermHealthStatus:
        if snapshot.lost_records > 10:
            return DecisionLongTermHealthStatus.CRITICAL
        if (
            snapshot.critical_divergences > 0
            or snapshot.error_rate > 0.1
            or trend in {TrendStatus.DEGRADING, TrendStatus.UNSTABLE}
        ):
            return DecisionLongTermHealthStatus.DEGRADED
        if snapshot.total_decisions < minimum_volume or snapshot.errors > 0 or snapshot.lost_records > 0:
            return DecisionLongTermHealthStatus.WARNING
        return DecisionLongTermHealthStatus.HEALTHY
