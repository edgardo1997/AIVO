from datetime import timedelta

import pytest
from pydantic import ValidationError

from sentinel.contracts import (
    AuthorizationScopeV1,
    ExecutionBoundaryDecisionV1,
    PolicyEvaluationStatusV1,
    SandboxCategoryV1,
    SandboxSimulationStatusV1,
)
from sentinel.execution_boundary import (
    ExecutionBoundaryControl,
    ExecutionRequestV1,
    PassiveExecutionBoundaryV2,
)
from sentinel.operational_telemetry_hub import OperationalTelemetryHub
from sentinel.sandbox_engine import (
    PassiveSandboxEngineV2,
    SandboxEngineControl,
    SandboxRequestV1,
)
from sentinel.tool_gateway import PassiveToolGatewayV2, ToolGatewayControl
from test_tool_gateway_v2 import _inputs


def _boundary_inputs(tmp_path):
    tool_request, grant, consent, evidence, policy, verifier = _inputs(tmp_path)
    gateway_hub = OperationalTelemetryHub(
        database_path=tmp_path / "boundary-gateway.sqlite3",
        enabled=True,
    )
    gateway = (
        PassiveToolGatewayV2(
            control=ToolGatewayControl(enabled=True),
            verifier=verifier,
            telemetry_hub=gateway_hub,
        )
        .evaluate(
            request=tool_request,
            grant=grant,
            consent=consent,
            evidence=evidence,
            policy=policy,
            now=tool_request.timestamp,
        )
        .decision
    )
    gateway_hub.close()
    sandbox_request = SandboxRequestV1(
        request_id="sandbox-request:boundary",
        correlation_id=gateway.correlation_id,
        evidence_hash=gateway.evidence_hash,
        issuer_id=gateway.issuer_id,
        authorization_reference=grant.grant_id,
        requested_category=SandboxCategoryV1.FILE_OPERATION,
        requested_scope=gateway.scope,
        timestamp=tool_request.timestamp + timedelta(seconds=1),
    )
    sandbox_hub = OperationalTelemetryHub(
        database_path=tmp_path / "boundary-sandbox.sqlite3",
        enabled=True,
    )
    simulation = (
        PassiveSandboxEngineV2(
            control=SandboxEngineControl(enabled=True),
            verifier=verifier,
            telemetry_hub=sandbox_hub,
        )
        .simulate(
            request=sandbox_request,
            gateway=gateway,
            grant=grant,
            evidence=evidence,
        )
        .simulation
    )
    sandbox_hub.close()
    request = ExecutionRequestV1(
        request_id="execution-request:one",
        correlation_id=simulation.correlation_id,
        evidence_hash=simulation.evidence_hash,
        issuer_id=simulation.issuer_id,
        authorization_reference=grant.grant_id,
        gateway_reference=gateway.decision_id,
        simulation_reference=simulation.simulation_id,
        policy_reference=policy.policy_id,
        action_category=simulation.requested_category,
        scope=simulation.affected_scope,
        simulation_status=simulation.status,
        timestamp=simulation.timestamp + timedelta(seconds=1),
    )
    return request, grant, gateway, simulation, policy, evidence, verifier


def _engine(tmp_path, verifier, *, enabled=True):
    telemetry = OperationalTelemetryHub(
        database_path=tmp_path / "execution-boundary.sqlite3",
        enabled=True,
    )
    engine = PassiveExecutionBoundaryV2(
        control=ExecutionBoundaryControl(enabled=enabled),
        verifier=verifier,
        telemetry_hub=telemetry,
    )
    return engine, telemetry


def test_boundary_is_deterministic_and_non_authoritative(tmp_path):
    values = _boundary_inputs(tmp_path)
    request, grant, gateway, simulation, policy, evidence, verifier = values
    engine, telemetry = _engine(tmp_path, verifier)
    try:
        kwargs = {
            "request": request,
            "grant": grant,
            "gateway": gateway,
            "simulation": simulation,
            "policy": policy,
            "evidence": evidence,
        }
        first = engine.evaluate(**kwargs)
        second = engine.evaluate(**kwargs)
        assert first.decision == second.decision
        assert first.decision.decision is (ExecutionBoundaryDecisionV1.EXECUTION_REVIEW_REQUIRED)
        assert first.decision.authority is False
        assert first.decision.execution_requested is False
        assert len(telemetry.timeline.latest()) == 1
    finally:
        telemetry.close()


def test_disabled_by_default_does_nothing(tmp_path):
    values = _boundary_inputs(tmp_path)
    request, grant, gateway, simulation, policy, evidence, verifier = values
    engine, telemetry = _engine(tmp_path, verifier, enabled=False)
    try:
        assert (
            engine.evaluate(
                request=request,
                grant=grant,
                gateway=gateway,
                simulation=simulation,
                policy=policy,
                evidence=evidence,
            )
            is None
        )
        assert telemetry.timeline.latest() == ()
    finally:
        telemetry.close()


def test_mismatched_origin_is_invalid(tmp_path):
    values = _boundary_inputs(tmp_path)
    request, grant, gateway, simulation, policy, evidence, verifier = values
    engine, telemetry = _engine(tmp_path, verifier)
    try:
        altered = request.model_copy(update={"correlation_id": "decision:other"})
        result = engine.evaluate(
            request=altered,
            grant=grant,
            gateway=gateway,
            simulation=simulation,
            policy=policy,
            evidence=evidence,
        )
        assert result.decision.decision is (ExecutionBoundaryDecisionV1.EXECUTION_INVALID)
        assert "CORRELATION_MISMATCH" in result.validation_errors
    finally:
        telemetry.close()


def test_scope_cannot_increase(tmp_path):
    values = _boundary_inputs(tmp_path)
    request, grant, gateway, simulation, policy, evidence, verifier = values
    engine, telemetry = _engine(tmp_path, verifier)
    try:
        elevated = request.model_copy(update={"scope": AuthorizationScopeV1.USER_APPROVED_ACTION})
        result = engine.evaluate(
            request=elevated,
            grant=grant,
            gateway=gateway,
            simulation=simulation,
            policy=policy,
            evidence=evidence,
        )
        assert "SCOPE_ESCALATION" in result.validation_errors
    finally:
        telemetry.close()


def test_expired_grant_and_invalid_evidence_are_invalid(tmp_path):
    values = _boundary_inputs(tmp_path)
    request, grant, gateway, simulation, policy, evidence, verifier = values
    engine, telemetry = _engine(tmp_path, verifier)
    try:
        late = request.model_copy(update={"timestamp": grant.expires_at + timedelta(seconds=1)})
        result = engine.evaluate(
            request=late,
            grant=grant,
            gateway=gateway,
            simulation=simulation,
            policy=policy,
            evidence=evidence.model_copy(update={"signature": "invalid-signature"}),
        )
        assert "CONSENT_OR_AUTHORIZATION_EXPIRED" in result.validation_errors
        assert any(item.startswith("EVIDENCE_") for item in result.validation_errors)
    finally:
        telemetry.close()


def test_blocking_policy_blocks_boundary(tmp_path):
    values = _boundary_inputs(tmp_path)
    request, grant, gateway, simulation, policy, evidence, verifier = values
    engine, telemetry = _engine(tmp_path, verifier)
    try:
        blocked_policy = policy.model_copy(update={"policy_status": PolicyEvaluationStatusV1.POLICY_BLOCKED})
        result = engine.evaluate(
            request=request,
            grant=grant,
            gateway=gateway,
            simulation=simulation,
            policy=blocked_policy,
            evidence=evidence,
        )
        assert result.decision.decision is (ExecutionBoundaryDecisionV1.EXECUTION_BLOCKED)
    finally:
        telemetry.close()


def test_request_rejects_executable_fields(tmp_path):
    request, *_ = _boundary_inputs(tmp_path)
    for field, value in (
        ("command", "delete C:\\Users\\private"),
        ("path", "C:\\Users\\private"),
        ("arguments", ("--force",)),
        ("script", "remove-item"),
        ("payload", {"secret": "x"}),
    ):
        with pytest.raises(ValidationError):
            ExecutionRequestV1(**request.model_dump(), **{field: value})


def test_result_is_immutable(tmp_path):
    values = _boundary_inputs(tmp_path)
    request, grant, gateway, simulation, policy, evidence, verifier = values
    engine, telemetry = _engine(tmp_path, verifier)
    try:
        result = engine.evaluate(
            request=request,
            grant=grant,
            gateway=gateway,
            simulation=simulation,
            policy=policy,
            evidence=evidence,
        ).decision
        with pytest.raises(ValidationError):
            result.authority = True
    finally:
        telemetry.close()
