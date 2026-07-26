"""Long-run stability validation over canary aggregate metrics."""

import uuid
from datetime import datetime, timezone

from .collector import StabilityCollector, StabilityMetrics
from .control import stability_validation_enabled
from .health import StabilityHealthEvaluator, StabilityStatus
from .report import StabilityReport
from .storage import StabilitySnapshotStorage
from .thresholds import ThresholdManager


_COMPONENTS = (
    "runtime_canary",
    "canary_observation",
    "policy_v2_shadow",
    "application_discovery_v2",
    "authorization_canary",
    "cutover_validation",
)


class StabilityValidationEngine:
    """Report stability only; never changes canary or runtime behavior."""

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        thresholds: ThresholdManager | None = None,
        storage: StabilitySnapshotStorage | None = None,
        collector: StabilityCollector | None = None,
    ) -> None:
        self._enabled = stability_validation_enabled() if enabled is None else enabled
        self.thresholds = thresholds or ThresholdManager()
        self.storage = storage or StabilitySnapshotStorage()
        self.collector = collector or StabilityCollector()
        self._health = StabilityHealthEvaluator()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def validate(
        self,
        component_metrics: dict[str, dict],
        *,
        started_at: datetime,
        ended_at: datetime | None = None,
    ) -> StabilityReport:
        end = ended_at or datetime.now(timezone.utc)
        _validate_times(started_at, end)
        duration = (end - started_at).total_seconds()
        if not self._enabled:
            return StabilityReport(
                validation_id="stability_validation_disabled",
                started_at=started_at,
                ended_at=end,
                observed_duration_seconds=duration,
                evaluated_components=(),
                status=StabilityStatus.WARNING,
                metrics=_empty_metrics(),
                warnings=("stability_validation_disabled",),
                blockers=(),
            )

        metrics = self.collector.collect(component_metrics)
        corruption = _metrics_corrupted(metrics)
        status, warnings, blockers = self._health.evaluate(
            metrics,
            thresholds=self.thresholds,
            storage_healthy=self.storage.healthy,
            data_complete=(duration >= self.thresholds.observation_window.total_seconds()),
        )
        if corruption:
            status = StabilityStatus.FAILED
            blockers = tuple(dict.fromkeys([*blockers, "metrics_corruption"]))
        report = StabilityReport(
            validation_id=f"stability_validation_{uuid.uuid4().hex}",
            started_at=started_at,
            ended_at=end,
            observed_duration_seconds=duration,
            evaluated_components=_COMPONENTS,
            status=status,
            metrics=metrics,
            warnings=warnings,
            blockers=blockers,
        )
        self.storage.save(report)
        return report


def _validate_times(started_at: datetime, ended_at: datetime) -> None:
    if (
        started_at.tzinfo is None
        or started_at.utcoffset() is None
        or ended_at.tzinfo is None
        or ended_at.utcoffset() is None
    ):
        raise ValueError("stability timestamps must be timezone-aware")
    if ended_at < started_at:
        raise ValueError("ended_at cannot be earlier than started_at")


def _metrics_corrupted(metrics: StabilityMetrics) -> bool:
    numeric = (
        metrics.total_events,
        metrics.processed_events,
        metrics.ignored_events,
        metrics.dropped_events,
        metrics.average_latency_ms,
        metrics.max_latency_ms,
        metrics.memory_start,
        metrics.memory_current,
        metrics.total_errors,
        metrics.consecutive_errors,
        metrics.comparison_matches,
        metrics.comparison_divergences,
        metrics.conversion_failures,
    )
    if any(value < 0 for value in numeric):
        return True
    accounted = metrics.processed_events + metrics.ignored_events + metrics.dropped_events
    return accounted > metrics.total_events


def _empty_metrics() -> StabilityMetrics:
    return StabilityMetrics(
        total_events=0,
        processed_events=0,
        ignored_events=0,
        dropped_events=0,
        average_latency_ms=0.0,
        max_latency_ms=0.0,
        latency_percentiles={"p50": 0.0, "p95": 0.0, "p99": 0.0},
        memory_start=0.0,
        memory_current=0.0,
        memory_delta=0.0,
        total_errors=0,
        consecutive_errors=0,
        error_rate=0.0,
        comparison_matches=0,
        comparison_divergences=0,
        conversion_failures=0,
    )
