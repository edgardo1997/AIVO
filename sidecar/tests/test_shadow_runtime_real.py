from copy import deepcopy
from datetime import timedelta

from pydantic import ValidationError
import pytest

from sentinel.contracts import (
    AuthorizationScopeV1,
    ConsentDecisionValueV1,
    PolicyEvaluationStatusV1,
)
from sentinel.operational_telemetry_hub import OperationalTelemetryHub
from sentinel.shadow_runtime_real import (
    DivergenceClassificationV1,
    DivergenceSeverityV1,
    LegacyRuntimeSnapshotV1,
    PassiveShadowRuntimeObserver,
    ShadowRuntimeRealControl,
    shadow_plan_fingerprint,
)
from sentinel.shadow_runtime_real.metrics import ShadowRuntimeMetrics
from sentinel.stability_validation import StabilityValidationEngine
from sentinel.stability_validation.health import StabilityStatus
from sentinel.stability_validation.thresholds import ThresholdManager
from sentinel.v2_unified_pipeline import (
    PassiveUnifiedPipelineV2,
    UnifiedPipelineControl,
)
from test_v2_unified_pipeline import _request


def _observer_inputs(tmp_path, metrics=None):
    request, verifier = _request(tmp_path)
    baseline_hub = OperationalTelemetryHub(
        database_path=tmp_path / "real-shadow-baseline.sqlite3",
        enabled=True,
    )
    baseline_pipeline = PassiveUnifiedPipelineV2(
        control=UnifiedPipelineControl(enabled=True),
        verifier=verifier,
        telemetry_hub=baseline_hub,
    )
    try:
        expected = baseline_pipeline.evaluate(
            request,
            consent_decision=ConsentDecisionValueV1.CONSENT_GRANTED,
            human_actor="human:reviewer",
        )
    finally:
        baseline_hub.close()
    policy_value = {
        PolicyEvaluationStatusV1.POLICY_ALLOWED: "ALLOW",
        PolicyEvaluationStatusV1.POLICY_REVIEW_REQUIRED: "REQUIRE_CONSENT",
        PolicyEvaluationStatusV1.POLICY_BLOCKED: "DENY",
        PolicyEvaluationStatusV1.POLICY_UNKNOWN: "UNKNOWN",
    }[expected.policy.policy_status]
    snapshot = LegacyRuntimeSnapshotV1(
        snapshot_id="legacy-snapshot:one",
        correlation_id=request.correlation_id,
        timestamp=request.timestamp,
        plan_fingerprint=shadow_plan_fingerprint(expected.plan),
        policy_decision=policy_value,
        scope=AuthorizationScopeV1.READ_ONLY,
        result_code=expected.status.value,
    )
    hub = OperationalTelemetryHub(
        database_path=tmp_path / "real-shadow.sqlite3",
        enabled=True,
    )
    pipeline = PassiveUnifiedPipelineV2(
        control=UnifiedPipelineControl(enabled=True),
        verifier=verifier,
        telemetry_hub=hub,
    )
    observer = PassiveShadowRuntimeObserver(
        control=ShadowRuntimeRealControl(enabled=True),
        pipeline=pipeline,
        metrics=metrics,
    )
    return observer, snapshot, request, hub


def _observe(observer, snapshot, request):
    return observer.observe(
        legacy_snapshot=snapshot,
        pipeline_request=request,
        consent_decision=ConsentDecisionValueV1.CONSENT_GRANTED,
        human_actor="human:reviewer",
    )


def test_real_snapshot_is_observed_without_mutating_legacy(tmp_path):
    observer, snapshot, request, hub = _observer_inputs(tmp_path)
    snapshot_before = deepcopy(snapshot.model_dump())
    request_before = deepcopy(request.model_dump())
    try:
        result = _observe(observer, snapshot, request)
        assert result.observed is True
        assert result.comparison.matched is True
        assert result.comparison.divergences == ()
        assert snapshot.model_dump() == snapshot_before
        assert request.model_dump() == request_before
        assert result.authority is False
        assert result.execution_requested is False
    finally:
        hub.close()


def test_critical_policy_divergence_is_classified(tmp_path):
    observer, snapshot, request, hub = _observer_inputs(tmp_path)
    snapshot = snapshot.model_copy(update={"policy_decision": "DENY"})
    try:
        result = _observe(observer, snapshot, request)
        policy = next(item for item in result.comparison.divergences if item.field == "POLICY")
        assert policy.classification is (DivergenceClassificationV1.CRITICAL_DIVERGENCE)
        assert policy.severity is DivergenceSeverityV1.CRITICAL
        assert result.comparison.critical_count == 1
    finally:
        hub.close()


def test_information_loss_is_measured(tmp_path):
    observer, snapshot, request, hub = _observer_inputs(tmp_path)
    snapshot = snapshot.model_copy(update={"lost_fields": ("ROLLBACK_METADATA",)})
    try:
        result = _observe(observer, snapshot, request)
        assert result.comparison.information_loss_count == 1
        assert observer.metrics_snapshot().information_losses == 1
    finally:
        hub.close()


@pytest.mark.parametrize(
    ("updates", "field", "critical"),
    (
        ({"plan_fingerprint": "0" * 64}, "PLAN", False),
        (
            {"scope": AuthorizationScopeV1.SIMULATION_ONLY},
            "SCOPE",
            False,
        ),
        ({"result_code": "FAILED"}, "RESULT", True),
    ),
)
def test_plan_scope_and_result_divergences_are_measured(
    tmp_path,
    updates,
    field,
    critical,
):
    observer, snapshot, request, hub = _observer_inputs(tmp_path)
    snapshot = snapshot.model_copy(update=updates)
    try:
        result = _observe(observer, snapshot, request)
        divergence = next(item for item in result.comparison.divergences if item.field == field)
        assert (divergence.severity is DivergenceSeverityV1.CRITICAL) is critical
    finally:
        hub.close()


def test_shadow_failure_isolated_from_legacy_copy(tmp_path, monkeypatch):
    observer, snapshot, request, hub = _observer_inputs(tmp_path)
    original = snapshot.model_dump()
    monkeypatch.setattr(
        observer.pipeline,
        "evaluate",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("shadow-only failure")),
    )
    try:
        result = _observe(observer, snapshot, request)
        assert result.observed is False
        assert result.error_code == "RUNTIMEERROR"
        assert snapshot.model_dump() == original
        assert observer.metrics_snapshot().failures == 1
    finally:
        hub.close()


def test_disabled_observer_does_not_run_pipeline(tmp_path, monkeypatch):
    observer, snapshot, request, hub = _observer_inputs(tmp_path)
    observer.control.enabled = False
    called = False

    def forbidden(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(observer.pipeline, "evaluate", forbidden)
    try:
        result = _observe(observer, snapshot, request)
        assert result.observed is False
        assert result.warnings == ("SHADOW_DISABLED",)
        assert called is False
        assert observer.metrics_snapshot().observations == 0
    finally:
        hub.close()


def test_snapshot_rejects_sensitive_or_unknown_payloads(tmp_path):
    _, snapshot, _, hub = _observer_inputs(tmp_path)
    try:
        with pytest.raises(ValidationError):
            LegacyRuntimeSnapshotV1(
                **snapshot.model_dump(),
                prompt="private request",
            )
    finally:
        hub.close()


def test_aggregate_metrics_feed_existing_stability_validator(tmp_path):
    metrics_store = ShadowRuntimeMetrics()
    snapshot = None
    for index in range(20):
        case_path = tmp_path / f"operation-{index}"
        case_path.mkdir()
        observer, current, request, hub = _observer_inputs(
            case_path,
            metrics=metrics_store,
        )
        try:
            result = _observe(observer, current, request)
            assert result.observed is True
            snapshot = current
        finally:
            hub.close()
    metrics = metrics_store.snapshot()
    assert metrics.observations == 20
    assert metrics.failures == 0
    assert metrics.critical_divergences == 0
    assert metrics.average_latency_ms >= 0

    validator = StabilityValidationEngine(
        enabled=True,
        thresholds=ThresholdManager(
            observation_window=timedelta(hours=72),
            max_latency_ms=max(metrics.maximum_latency_ms + 1, 250),
        ),
    )
    assert snapshot is not None
    report = validator.validate(
        metrics_store.stability_payload(),
        started_at=snapshot.timestamp,
        ended_at=snapshot.timestamp + timedelta(hours=72),
    )
    assert report.status is StabilityStatus.HEALTHY
