import pytest

from sentinel.controlled_runtime_activation import (
    ActivationAudit,
    ActivationHealthEvaluator,
    ActivationHealthStatus,
    ActivationMetrics,
    ActivationReport,
    ActivationState,
)


def test_metrics_are_aggregate_only() -> None:
    metrics = ActivationMetrics()
    metrics.record_route(v2=False, blocked=True)
    metrics.record_route(v2=True)
    metrics.record_rollback()
    metrics.record_failure()
    snapshot = metrics.snapshot()
    assert snapshot.total_requests == 2
    assert snapshot.legacy_requests == 1
    assert snapshot.v2_canary_requests == 1
    assert snapshot.rollbacks == 1
    assert snapshot.failures == 1
    assert snapshot.blocked_requests == 1
    assert not hasattr(metrics, "requests")
    assert not hasattr(metrics, "payloads")


def test_audit_is_sanitized_and_report_is_aggregate() -> None:
    audit = ActivationAudit()
    audit.record("activation_started", "CANARY_ACTIVE")
    assert audit.snapshot()[0].timestamp.utcoffset() is not None
    with pytest.raises(ValueError):
        audit.record("prompt_saved", "SECRET")
    with pytest.raises(ValueError):
        audit.record("legacy_selected", "private prompt")
    metrics = ActivationMetrics().snapshot()
    health = ActivationHealthEvaluator().evaluate(metrics)
    assert health is ActivationHealthStatus.HEALTHY
    report = ActivationReport(
        state=ActivationState.LEGACY_ONLY,
        health=health,
        metrics=metrics,
        risks=(),
        recommendation="KEEP_LEGACY_DEFAULT",
    )
    assert report.human_readable().startswith("SENTINEL CONTROLLED RUNTIME ACTIVATION REPORT")
