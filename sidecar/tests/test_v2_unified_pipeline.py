from datetime import timedelta
import hashlib

import pytest

from sentinel.contracts import (
    AuthorizationScopeV1,
    ConsentDecisionValueV1,
    IntentV2,
    SandboxCategoryV1,
    ToolCategoryV1,
)
from sentinel.operational_telemetry_hub import OperationalTelemetryHub
from sentinel.v2_unified_pipeline import (
    PassiveUnifiedPipelineV2,
    UnifiedPipelineControl,
    UnifiedPipelineRequestV1,
    UnifiedPipelineStatusV1,
)
from test_consent_manager_v2 import _signed_policy_inputs


def _request(tmp_path):
    values, _, verifier = _signed_policy_inputs(tmp_path / "inputs")
    evidence = values["evidence"]
    request = UnifiedPipelineRequestV1(
        correlation_id=evidence.correlation_id,
        intent=IntentV2(
            schema_version="2.0",
            intent_id="intent:unified-pipeline",
            action="analyze",
            target="file",
            parameters={},
            confidence=0.95,
            raw_input="analyze a hypothetical file operation",
        ),
        decision=values["decision"],
        recommendation=values["recommendation"],
        simulation=values["simulation"],
        evidence=evidence,
        trust=values["trust"],
        readiness=values["readiness"],
        health=values["health"],
        authorization_scope=AuthorizationScopeV1.READ_ONLY,
        parameters_hash=hashlib.sha256(b"{}").hexdigest(),
        tool_category=ToolCategoryV1.FILE_READ,
        sandbox_category=SandboxCategoryV1.FILE_OPERATION,
        timestamp=evidence.created_at + timedelta(minutes=1),
        consent_expires_at=evidence.created_at + timedelta(minutes=15),
        authorization_expires_at=evidence.created_at + timedelta(minutes=10),
    )
    return request, verifier


def _pipeline(tmp_path, verifier, *, enabled=True, telemetry=True):
    hub = OperationalTelemetryHub(
        database_path=tmp_path / "unified-pipeline.sqlite3",
        enabled=telemetry,
    )
    pipeline = PassiveUnifiedPipelineV2(
        control=UnifiedPipelineControl(enabled=enabled),
        verifier=verifier,
        telemetry_hub=hub,
    )
    return pipeline, hub


def test_contractual_pipeline_reaches_passive_isolation(tmp_path):
    request, verifier = _request(tmp_path)
    pipeline, hub = _pipeline(tmp_path, verifier)
    try:
        result = pipeline.evaluate(
            request,
            consent_decision=ConsentDecisionValueV1.CONSENT_GRANTED,
            human_actor="human:reviewer",
        )
        assert result.status is UnifiedPipelineStatusV1.COMPLETED
        assert result.completed_stages == (
            "intent",
            "policy",
            "consent",
            "authorization",
            "tool_gateway",
            "sandbox",
            "boundary",
            "planner",
            "executor_sandbox",
            "isolation",
        )
        assert result.isolation is not None
        assert result.authority is False
        assert result.execution_requested is False

        contracts = (
            result.policy,
            result.consent,
            result.authorization,
            result.gateway,
            result.sandbox,
            result.boundary,
            result.plan,
            result.sandbox_execution,
            result.isolation,
        )
        assert all(item.correlation_id == request.correlation_id for item in contracts)
        assert all(item.evidence_hash == request.evidence.payload_hash for item in contracts)
        assert all(item.authority is False for item in contracts)
        assert all(item.execution_requested is False for item in contracts)
        events = hub.timeline.latest(limit=50)
        assert len(events) >= 10
        assert {event.correlation_id for event in events} == {request.correlation_id}
        assert {event.evidence_hash for event in events} == {request.evidence.payload_hash}
    finally:
        hub.close()


def test_pipeline_waits_for_explicit_human_consent(tmp_path):
    request, verifier = _request(tmp_path)
    pipeline, hub = _pipeline(tmp_path, verifier)
    try:
        result = pipeline.evaluate(request)
        assert result.status is UnifiedPipelineStatusV1.AWAITING_CONSENT
        assert result.consent.decision is (ConsentDecisionValueV1.CONSENT_PENDING)
        assert result.authorization is None
        assert result.authority is False
        assert result.execution_requested is False
    finally:
        hub.close()


def test_pipeline_fails_closed_on_invalid_evidence(tmp_path):
    request, verifier = _request(tmp_path)
    request = request.model_copy(update={"evidence": request.evidence.model_copy(update={"signature": "A" * 86})})
    pipeline, hub = _pipeline(tmp_path, verifier)
    try:
        result = pipeline.evaluate(
            request,
            consent_decision=ConsentDecisionValueV1.CONSENT_GRANTED,
            human_actor="human:reviewer",
        )
        assert result.status is UnifiedPipelineStatusV1.BLOCKED
        assert result.failed_stage == "consent"
        assert result.authorization is None
        assert result.isolation is None
    finally:
        hub.close()


def test_pipeline_requires_shared_telemetry(tmp_path):
    request, verifier = _request(tmp_path)
    pipeline, hub = _pipeline(tmp_path, verifier, telemetry=False)
    try:
        result = pipeline.evaluate(request)
        assert result.status is UnifiedPipelineStatusV1.INVALID
        assert result.failed_stage == "telemetry"
        assert result.errors == ("TELEMETRY_REQUIRED",)
    finally:
        hub.close()


def test_pipeline_is_disabled_by_default(tmp_path):
    request, verifier = _request(tmp_path)
    pipeline, hub = _pipeline(tmp_path, verifier, enabled=False)
    try:
        result = pipeline.evaluate(request)
        assert result.status is UnifiedPipelineStatusV1.DISABLED
        assert hub.timeline.latest() == ()
    finally:
        hub.close()


@pytest.mark.parametrize(
    ("target", "stage"),
    (
        (
            "sentinel.v2_unified_pipeline.pipeline.PassivePolicyEngine.evaluate",
            "policy",
        ),
        (
            "sentinel.v2_unified_pipeline.pipeline.ConsentManagerV2.request",
            "consent",
        ),
        (
            "sentinel.v2_unified_pipeline.pipeline.AuthorizationManagerV2.request",
            "authorization",
        ),
        (
            "sentinel.v2_unified_pipeline.pipeline.PassiveToolGatewayV2.evaluate",
            "tool_gateway",
        ),
        (
            "sentinel.v2_unified_pipeline.pipeline.PassiveSandboxEngineV2.simulate",
            "sandbox",
        ),
        (
            "sentinel.v2_unified_pipeline.pipeline.PassiveExecutionBoundaryV2.evaluate",
            "boundary",
        ),
        (
            "sentinel.v2_unified_pipeline.pipeline.PassiveExecutionPlannerV2.create_plan",
            "planner",
        ),
        (
            "sentinel.v2_unified_pipeline.pipeline.PassiveExecutorSandboxV2.simulate",
            "executor_sandbox",
        ),
        (
            "sentinel.v2_unified_pipeline.pipeline.PassiveRuntimeIsolationV2.evaluate",
            "isolation",
        ),
    ),
)
def test_every_stage_fails_closed(tmp_path, monkeypatch, target, stage):
    request, verifier = _request(tmp_path)
    pipeline, hub = _pipeline(tmp_path, verifier)
    monkeypatch.setattr(target, lambda *args, **kwargs: None)
    try:
        result = pipeline.evaluate(
            request,
            consent_decision=ConsentDecisionValueV1.CONSENT_GRANTED,
            human_actor="human:reviewer",
        )
        assert result.status is UnifiedPipelineStatusV1.BLOCKED
        assert result.failed_stage == stage
        assert result.isolation is None
        assert result.authority is False
        assert result.execution_requested is False
    finally:
        hub.close()
