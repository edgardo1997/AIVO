from sentinel.v2_operational_observability import (
    V2_OPERATIONAL_OBSERVABILITY_ENABLED,
    AlertRecommendation,
    IncidentClassification,
    ObservationBatchV1,
    OperationalHealthStatus,
    OperationalObserver,
    V2OperationalObservabilityControl,
)


def batch(**updates):
    values = {
        "correlation_hash": "a" * 64,
        "legacy_decisions": 10,
        "v2_decisions": 1,
        "canary_active": True,
        "rollback_events": 0,
        "total_events": 10,
        "errors": 0,
        "divergences": 0,
        "critical_divergences": 0,
        "lost_events": 0,
        "average_latency_ms": 10,
        "stable": True,
        "state_corrupted": False,
        "health_failed": False,
        "trial_expired": False,
        "canary_duration_seconds": 60,
    }
    values.update(updates)
    return ObservationBatchV1(**values)


def test_disabled_by_default_creates_no_timeline_or_events() -> None:
    assert V2_OPERATIONAL_OBSERVABILITY_ENABLED is False
    observer = OperationalObserver(control=V2OperationalObservabilityControl(environ={}))
    assert observer.timeline is None
    assert observer.observe(batch()) is None
    assert observer.metrics.snapshot().total_events == 0


def test_healthy_observation_is_non_authoritative() -> None:
    observer = OperationalObserver(control=V2OperationalObservabilityControl(enabled=True))
    result = observer.observe(batch())
    assert result.incident is IncidentClassification.INCIDENT_NONE
    assert result.recommendation is AlertRecommendation.NO_ACTION
    assert result.health is OperationalHealthStatus.HEALTHY
    assert result.authority is False
    assert result.execution_requested is False
    assert observer.timeline.snapshot()[0].event_type == "canary_started"


def test_trial_expiration_only_recommends_monitoring() -> None:
    observer = OperationalObserver(control=V2OperationalObservabilityControl(enabled=True))
    result = observer.observe(batch(trial_expired=True))
    assert result.incident is IncidentClassification.INCIDENT_WARNING
    assert result.recommendation is AlertRecommendation.MONITOR
