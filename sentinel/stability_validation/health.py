"""Operational stability classification over aggregate metrics."""

from enum import Enum

from .collector import StabilityMetrics
from .thresholds import ThresholdManager


class StabilityStatus(str, Enum):
    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    UNSTABLE = "UNSTABLE"
    FAILED = "FAILED"


class StabilityHealthEvaluator:
    def evaluate(
        self,
        metrics: StabilityMetrics,
        *,
        thresholds: ThresholdManager,
        storage_healthy: bool,
        data_complete: bool,
    ) -> tuple[StabilityStatus, tuple[str, ...], tuple[str, ...]]:
        blockers: list[str] = []
        warnings: list[str] = []
        if not storage_healthy:
            blockers.append("metrics_storage_corruption")
        if not metrics.observer_stable:
            blockers.append("observer_instability")
        if metrics.consecutive_errors >= thresholds.critical_consecutive_errors:
            blockers.append("critical_consecutive_errors")
        if blockers:
            return StabilityStatus.FAILED, tuple(warnings), tuple(blockers)

        dropped_rate = metrics.dropped_events / metrics.total_events if metrics.total_events > 0 else 0.0
        unstable = []
        if metrics.memory_delta > thresholds.memory_limit_mb:
            unstable.append("progressive_memory_growth")
        if dropped_rate > thresholds.max_dropped_event_rate:
            unstable.append("frequent_event_loss")
        if metrics.error_rate > thresholds.error_rate_limit:
            unstable.append("sustained_error_rate")
        if metrics.max_latency_ms > thresholds.max_latency_ms * 2:
            unstable.append("severe_latency")
        if unstable:
            return StabilityStatus.UNSTABLE, tuple(unstable), ()

        if not data_complete:
            warnings.append("incomplete_observation_window")
        if metrics.memory_delta > thresholds.memory_limit_mb * thresholds.warning_memory_ratio:
            warnings.append("moderate_memory_growth")
        if dropped_rate > thresholds.max_dropped_event_rate / 2:
            warnings.append("moderate_event_loss")
        if metrics.max_latency_ms > thresholds.max_latency_ms:
            warnings.append("elevated_latency")
        if metrics.total_events == 0:
            warnings.append("insufficient_events")
        if warnings:
            return StabilityStatus.WARNING, tuple(warnings), ()
        return StabilityStatus.HEALTHY, (), ()
