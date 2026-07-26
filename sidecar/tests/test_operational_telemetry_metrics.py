from sentinel.contracts import EvidenceIntegrityStatusV1, HealthStateV1
from sentinel.operational_telemetry_hub import (
    OperationalEventFactory,
    OperationalMetricAggregator,
    OperationalTelemetryHealth,
)


def _event(
    event_type: str,
    *,
    health: HealthStateV1 = HealthStateV1.HEALTHY,
    decision: str = "MATCH",
):
    event = OperationalEventFactory.synthetic(
        correlation_id="correlation-1",
        evidence_hash="c" * 64,
        issuer_id="issuer.telemetry.v1",
        event_type=event_type,
        health_state=health,
        decision_state=decision,
    )
    return event.model_copy(update={"integrity_status": EvidenceIntegrityStatusV1.VERIFIED})


def test_metrics_are_aggregate_and_sanitized():
    metrics = OperationalMetricAggregator()
    metrics.record(_event("POLICY_DECISION"))
    metrics.record(_event("CRITICAL_DIVERGENCE", health=HealthStateV1.WARNING))
    metrics.record(_event("ROLLBACK_EVENT", decision="FAILED"))
    metrics.record(_event("CANARY_OBSERVATION"))
    snapshot = metrics.snapshot()

    assert snapshot.decisions == 1
    assert snapshot.divergences == 1
    assert snapshot.errors == 1
    assert snapshot.rollbacks == 1
    assert snapshot.health_transitions == 2
    assert snapshot.evidence_verified == 4
    assert snapshot.canary_observations == 1
    assert snapshot.authority is False
    assert snapshot.execution_requested is False
    assert not hasattr(snapshot, "events")
    assert not hasattr(snapshot, "payloads")


def test_health_uses_only_aggregate_metrics():
    metrics = OperationalMetricAggregator()
    observing = OperationalTelemetryHealth.evaluate(metrics.snapshot())
    assert observing.state is HealthStateV1.OBSERVING
    metrics.record(_event("ERROR_EVENT", decision="FAILED"))
    health = OperationalTelemetryHealth.evaluate(metrics.snapshot())
    assert health.state is HealthStateV1.DEGRADED
