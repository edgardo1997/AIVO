"""Health classification over trial aggregates."""

from sentinel.contracts import HealthStateV1

from .metrics import RuntimeTrialMetricsSnapshot

RuntimeTrialHealthStatus = HealthStateV1


class RuntimeTrialHealthEvaluator:
    def evaluate(
        self,
        metrics: RuntimeTrialMetricsSnapshot,
        *,
        isolated: bool = True,
    ) -> RuntimeTrialHealthStatus:
        if not isolated:
            return RuntimeTrialHealthStatus.CRITICAL
        if metrics.scenarios_run == 0:
            return RuntimeTrialHealthStatus.WARNING
        failure_rate = metrics.failures / metrics.scenarios_run
        if failure_rate > 0.5 or metrics.maximum_latency_ms > 5000:
            return RuntimeTrialHealthStatus.DEGRADED
        if metrics.failures or metrics.divergences:
            return RuntimeTrialHealthStatus.WARNING
        return RuntimeTrialHealthStatus.HEALTHY
