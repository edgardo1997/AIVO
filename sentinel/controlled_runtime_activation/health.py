"""Health classification over aggregate activation metrics."""

from sentinel.contracts import HealthStateV1

from .metrics import ActivationMetricsSnapshot

ActivationHealthStatus = HealthStateV1


class ActivationHealthEvaluator:
    def evaluate(
        self,
        metrics: ActivationMetricsSnapshot,
    ) -> ActivationHealthStatus:
        if metrics.failures > 0 or metrics.rollbacks > 0:
            return ActivationHealthStatus.CRITICAL
        if metrics.blocked_requests > 0:
            return ActivationHealthStatus.WARNING
        return ActivationHealthStatus.HEALTHY
