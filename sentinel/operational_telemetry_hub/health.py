"""Health evaluation based only on consolidated aggregate metrics."""

from sentinel.contracts import HealthStateV1, HealthStatusV1

from .metrics import OperationalMetricSnapshotV1


class OperationalTelemetryHealth:
    @staticmethod
    def evaluate(snapshot: OperationalMetricSnapshotV1) -> HealthStatusV1:
        if snapshot.errors >= 10:
            state = HealthStateV1.CRITICAL
        elif snapshot.errors or snapshot.divergences >= 5:
            state = HealthStateV1.DEGRADED
        elif snapshot.divergences or snapshot.rollbacks:
            state = HealthStateV1.WARNING
        elif snapshot.decisions == 0 and snapshot.canary_observations == 0:
            state = HealthStateV1.OBSERVING
        else:
            state = HealthStateV1.HEALTHY
        return HealthStatusV1(state=state)
