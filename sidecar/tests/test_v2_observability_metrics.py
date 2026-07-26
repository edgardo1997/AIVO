import pytest

from sentinel.v2_operational_observability import (
    AlertRecommendation,
    OperationalHealthStatus,
    OperationalMetrics,
    OperationalReport,
    OperationalTimeline,
)


def test_metrics_are_aggregate_only() -> None:
    metrics = OperationalMetrics()
    metrics.record(
        events=100,
        errors=5,
        divergences=2,
        rollbacks=1,
        canary_duration_seconds=60,
        health_changed=True,
        incident=True,
    )
    snapshot = metrics.snapshot()
    assert snapshot.total_events == 100
    assert snapshot.error_rate == 0.05
    assert snapshot.divergence_rate == 0.02
    assert snapshot.rollback_count == 1
    assert snapshot.canary_duration_seconds == 60
    assert snapshot.health_changes == 1
    assert snapshot.incident_count == 1
    assert not hasattr(metrics, "events")
    assert not hasattr(metrics, "payloads")


def test_timeline_accepts_only_sanitized_fields() -> None:
    timeline = OperationalTimeline()
    timeline.append(
        event_type="activation_attempt",
        correlation_hash="c" * 64,
        sanitized_result="OBSERVED",
    )
    assert timeline.snapshot()[0].timestamp.utcoffset() is not None
    with pytest.raises(ValueError):
        timeline.append(
            event_type="activation_attempt",
            correlation_hash="not-a-hash",
            sanitized_result="private prompt",
        )


def test_report_is_aggregate() -> None:
    metrics = OperationalMetrics().snapshot()
    report = OperationalReport(
        current_health=OperationalHealthStatus.OBSERVING,
        incidents_detected=0,
        metrics=metrics,
        recommendations=(AlertRecommendation.MONITOR,),
        risks=("INSUFFICIENT_DATA",),
    )
    assert report.human_readable().startswith("SENTINEL V2 OPERATIONAL OBSERVABILITY REPORT")
