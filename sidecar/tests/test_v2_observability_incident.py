from sentinel.v2_operational_observability import (
    AlertRecommendation,
    IncidentClassification,
    ObservationBatchV1,
    OperationalObserver,
    V2OperationalObservabilityControl,
)


def observe(**updates):
    values = {
        "correlation_hash": "b" * 64,
        "legacy_decisions": 100,
        "v2_decisions": 10,
        "canary_active": True,
        "rollback_events": 0,
        "total_events": 100,
        "errors": 0,
        "divergences": 0,
        "critical_divergences": 0,
        "lost_events": 0,
        "average_latency_ms": 10,
        "stable": True,
        "state_corrupted": False,
        "health_failed": False,
        "trial_expired": False,
        "canary_duration_seconds": 120,
    }
    values.update(updates)
    observer = OperationalObserver(control=V2OperationalObservabilityControl(enabled=True))
    return observer, observer.observe(ObservationBatchV1(**values))


def test_error_increase_is_critical() -> None:
    _, result = observe(errors=20)
    assert result.incident is IncidentClassification.INCIDENT_CRITICAL
    assert result.recommendation is AlertRecommendation.PAUSE_CANARY


def test_critical_divergence_recommends_rollback_only() -> None:
    observer, result = observe(
        divergences=1,
        critical_divergences=1,
    )
    assert result.incident is (IncidentClassification.INCIDENT_ROLLBACK_REQUIRED)
    assert result.recommendation is AlertRecommendation.TRIGGER_ROLLBACK
    assert result.execution_requested is False
    assert observer.timeline.snapshot()[0].event_type == "divergence_detected"


def test_corruption_blocks_future_activation_recommendation() -> None:
    _, result = observe(state_corrupted=True)
    assert result.recommendation is (AlertRecommendation.BLOCK_FUTURE_ACTIVATION)


def test_event_loss_is_detected() -> None:
    _, warning = observe(lost_events=1)
    _, critical = observe(lost_events=11)
    assert warning.incident is IncidentClassification.INCIDENT_WARNING
    assert critical.incident is IncidentClassification.INCIDENT_CRITICAL
