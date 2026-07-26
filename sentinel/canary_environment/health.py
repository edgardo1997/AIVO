"""Health classification from aggregate canary signals."""

from sentinel.contracts import HealthStateV1

from .metrics import CanaryMetricsSnapshot

CanaryHealthStatus = HealthStateV1


class CanaryHealthEvaluator:
    def evaluate(
        self,
        metrics: CanaryMetricsSnapshot,
        *,
        consecutive_errors: int = 0,
        memory_mb: float = 0,
        memory_limit_mb: float = 128,
        dropped_events: int = 0,
        critical_divergences: int = 0,
    ) -> tuple[CanaryHealthStatus, tuple[str, ...]]:
        if consecutive_errors >= 10:
            return CanaryHealthStatus.CRITICAL, ("critical_error_streak",)
        if memory_mb > memory_limit_mb * 1.5:
            return CanaryHealthStatus.CRITICAL, ("memory_limit_exceeded",)
        if critical_divergences > 0 or dropped_events >= 10:
            return CanaryHealthStatus.DEGRADED, ("critical_divergence_or_event_loss",)
        error_rate = metrics.errors / max(metrics.processed_events, 1)
        if error_rate > 0.1 or metrics.maximum_latency_ms > 5000 or metrics.failed_conversions > 5:
            return CanaryHealthStatus.DEGRADED, ("operational_instability",)
        if (
            error_rate > 0
            or metrics.maximum_latency_ms > 1000
            or memory_mb > memory_limit_mb * 0.8
            or dropped_events > 0
        ):
            return CanaryHealthStatus.WARNING, ("threshold_warning",)
        return CanaryHealthStatus.HEALTHY, ()
