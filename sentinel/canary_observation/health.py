"""Read-only health classification for canary observation."""

from sentinel.contracts import HealthStateV1, HealthStatusV1

from .aggregation import CanaryMetricsAggregator

CanaryHealthStatus = HealthStateV1


class CanaryHealthReport(HealthStatusV1):
    reasons: tuple[str, ...]

    @property
    def status(self) -> CanaryHealthStatus:
        return self.state


class CanaryHealth:
    def __init__(
        self,
        *,
        max_consecutive_errors: int = 5,
        latency_warning_ms: float = 250.0,
    ) -> None:
        self.max_consecutive_errors = max_consecutive_errors
        self.latency_warning_ms = latency_warning_ms
        self.consecutive_errors = 0
        self.maximum_latency_ms = 0.0

    def record(self, *, failed: bool, latency_ms: float) -> None:
        self.consecutive_errors = self.consecutive_errors + 1 if failed else 0
        self.maximum_latency_ms = max(
            self.maximum_latency_ms,
            latency_ms,
        )

    def evaluate(
        self,
        *,
        enabled: bool,
        aggregator: CanaryMetricsAggregator,
    ) -> CanaryHealthReport:
        if not enabled:
            return CanaryHealthReport(
                state=CanaryHealthStatus.OBSERVING,
                reasons=("observation_disabled",),
            )
        reasons: list[str] = []
        if not aggregator.storage.healthy:
            reasons.append("storage_corruption")
        if self.consecutive_errors >= self.max_consecutive_errors:
            reasons.append("excessive_consecutive_errors")
        if self.maximum_latency_ms > self.latency_warning_ms:
            reasons.append("abnormal_latency")
        if aggregator.events_dropped:
            reasons.append("event_loss")
        if aggregator.capacity and aggregator.recent_count >= aggregator.capacity:
            reasons.append("memory_growth")
        if {
            "storage_corruption",
            "excessive_consecutive_errors",
        } & set(reasons):
            status = CanaryHealthStatus.CRITICAL
        elif reasons:
            status = CanaryHealthStatus.WARNING
        else:
            status = CanaryHealthStatus.HEALTHY
        return CanaryHealthReport(state=status, reasons=tuple(reasons))
