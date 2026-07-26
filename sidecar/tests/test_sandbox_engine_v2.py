from datetime import timedelta

import pytest
from pydantic import ValidationError

from sentinel.contracts import (
    AuthorizationScopeV1,
    EvidenceIntegrityStatusV1,
    SandboxCategoryV1,
    SandboxSimulationStatusV1,
    SimulationRiskLevelV1,
    ToolGatewayDecisionValueV1,
)
from sentinel.operational_telemetry_hub import OperationalTelemetryHub
from sentinel.sandbox_engine import (
    PassiveSandboxEngineV2,
    SandboxEngineControl,
    SandboxRequestV1,
)
from sentinel.tool_gateway import PassiveToolGatewayV2, ToolGatewayControl
from test_tool_gateway_v2 import _inputs


def _sandbox_inputs(tmp_path):
    request, grant, consent, evidence, policy, verifier = _inputs(tmp_path)
    gateway_telemetry = OperationalTelemetryHub(
        database_path=tmp_path / "gateway-source.sqlite3",
        enabled=True,
    )
    gateway_engine = PassiveToolGatewayV2(
        control=ToolGatewayControl(enabled=True),
        verifier=verifier,
        telemetry_hub=gateway_telemetry,
    )
    gateway = gateway_engine.evaluate(
        request=request,
        grant=grant,
        consent=consent,
        evidence=evidence,
        policy=policy,
        now=request.timestamp,
    ).decision
    gateway_telemetry.close()
    sandbox_request = SandboxRequestV1(
        request_id="sandbox-request:one",
        correlation_id=gateway.correlation_id,
        evidence_hash=gateway.evidence_hash,
        issuer_id=gateway.issuer_id,
        authorization_reference=gateway.authorization_reference,
        requested_category=SandboxCategoryV1.FILE_OPERATION,
        requested_scope=gateway.scope,
        timestamp=request.timestamp + timedelta(seconds=1),
    )
    return sandbox_request, gateway, grant, evidence, verifier


def _engine(tmp_path, verifier, *, enabled=True):
    telemetry = OperationalTelemetryHub(
        database_path=tmp_path / "sandbox.sqlite3",
        enabled=True,
    )
    engine = PassiveSandboxEngineV2(
        control=SandboxEngineControl(enabled=enabled),
        verifier=verifier,
        telemetry_hub=telemetry,
    )
    return engine, telemetry


def test_simulation_is_deterministic_safe_and_non_authoritative(tmp_path):
    request, gateway, grant, evidence, verifier = _sandbox_inputs(tmp_path)
    engine, telemetry = _engine(tmp_path, verifier)
    try:
        kwargs = {
            "request": request,
            "gateway": gateway,
            "grant": grant,
            "evidence": evidence,
        }
        first = engine.simulate(**kwargs)
        second = engine.simulate(**kwargs)
        assert first.simulation == second.simulation
        assert first.simulation.status is (SandboxSimulationStatusV1.SIMULATION_WARNING)
        assert first.simulation.authority is False
        assert first.simulation.execution_requested is False
        assert first.environment.environment_type == "CONTRACT_ONLY"
        assert first.environment.system_access is False
        assert len(telemetry.timeline.latest()) == 1
    finally:
        telemetry.close()


def test_invalid_evidence_and_expired_grant_block_simulation(tmp_path):
    request, gateway, grant, evidence, verifier = _sandbox_inputs(tmp_path)
    engine, telemetry = _engine(tmp_path, verifier)
    try:
        invalid = evidence.model_copy(update={"integrity_status": EvidenceIntegrityStatusV1.INVALID})
        invalid_result = engine.simulate(
            request=request,
            gateway=gateway,
            grant=grant,
            evidence=invalid,
        )
        assert invalid_result.simulation.status is (SandboxSimulationStatusV1.SIMULATION_BLOCKED)
        assert "EVIDENCE_NOT_VERIFIED" in invalid_result.validation_errors

        late_request = request.model_copy(
            update={
                "request_id": "sandbox-request:late",
                "timestamp": grant.expires_at + timedelta(seconds=1),
            }
        )
        expired = engine.simulate(
            request=late_request,
            gateway=gateway,
            grant=grant,
            evidence=evidence,
        )
        assert "AUTHORIZATION_EXPIRED" in expired.validation_errors
        assert expired.simulation.status is (SandboxSimulationStatusV1.SIMULATION_BLOCKED)
    finally:
        telemetry.close()


def test_blocked_gateway_and_critical_risk_block_simulation(tmp_path):
    request, gateway, grant, evidence, verifier = _sandbox_inputs(tmp_path)
    engine, telemetry = _engine(tmp_path, verifier)
    try:
        blocked_gateway = gateway.model_copy(update={"decision": ToolGatewayDecisionValueV1.TOOL_BLOCKED})
        blocked = engine.simulate(
            request=request,
            gateway=blocked_gateway,
            grant=grant,
            evidence=evidence,
        )
        assert "GATEWAY_DECISION_BLOCKS_SIMULATION" in (blocked.validation_errors)

        critical_gateway = gateway.model_copy(update={"risk_level": SimulationRiskLevelV1.CRITICAL})
        critical = engine.simulate(
            request=request.model_copy(update={"request_id": "sandbox-request:critical"}),
            gateway=critical_gateway,
            grant=grant,
            evidence=evidence,
        )
        assert critical.simulation.status is (SandboxSimulationStatusV1.SIMULATION_BLOCKED)
    finally:
        telemetry.close()


def test_scope_correlation_evidence_and_issuer_cannot_increase_or_diverge(
    tmp_path,
):
    request, gateway, grant, evidence, verifier = _sandbox_inputs(tmp_path)
    engine, telemetry = _engine(tmp_path, verifier)
    try:
        altered = request.model_copy(
            update={
                "requested_scope": AuthorizationScopeV1.USER_APPROVED_ACTION,
                "correlation_id": "decision:different",
                "evidence_hash": "b" * 64,
                "issuer_id": "other.issuer",
            }
        )
        result = engine.simulate(
            request=altered,
            gateway=gateway,
            grant=grant,
            evidence=evidence,
        )
        assert {
            "SCOPE_ESCALATION",
            "CORRELATION_MISMATCH",
            "EVIDENCE_HASH_MISMATCH",
            "ISSUER_MISMATCH",
        }.issubset(result.validation_errors)
        assert result.simulation.status is (SandboxSimulationStatusV1.SIMULATION_BLOCKED)
    finally:
        telemetry.close()


def test_impact_and_rollback_are_predictions_only(tmp_path):
    request, gateway, grant, evidence, verifier = _sandbox_inputs(tmp_path)
    engine, telemetry = _engine(tmp_path, verifier)
    try:
        result = engine.simulate(
            request=request,
            gateway=gateway,
            grant=grant,
            evidence=evidence,
        )
        assert result.simulation.estimated_impact == ("Potential modification of data.")
        assert result.simulation.rollback_available is True
    finally:
        telemetry.close()


def test_result_is_immutable_and_request_rejects_sensitive_fields(tmp_path):
    request, gateway, grant, evidence, verifier = _sandbox_inputs(tmp_path)
    engine, telemetry = _engine(tmp_path, verifier)
    try:
        result = engine.simulate(
            request=request,
            gateway=gateway,
            grant=grant,
            evidence=evidence,
        )
        with pytest.raises(ValidationError):
            result.simulation.confidence = 0
        base = request.model_dump()
        for field in (
            "path",
            "command",
            "script",
            "arguments",
            "private_content",
            "secret",
            "credential",
        ):
            with pytest.raises(ValidationError):
                SandboxRequestV1.model_validate({**base, field: "forbidden"})
    finally:
        telemetry.close()


def test_sandbox_generates_audit_timeline_and_metric_snapshot(tmp_path):
    request, gateway, grant, evidence, verifier = _sandbox_inputs(tmp_path)
    engine, telemetry = _engine(tmp_path, verifier)
    try:
        result = engine.simulate(
            request=request,
            gateway=gateway,
            grant=grant,
            evidence=evidence,
        )
        assert result.audit_event.result == result.simulation.status.value
        assert telemetry.timeline.latest() == (result.operational_event,)
        assert result.telemetry_snapshot is not None
        assert result.metrics.simulations_total == 1
    finally:
        telemetry.close()


def test_sandbox_is_disabled_by_default(tmp_path):
    request, gateway, grant, evidence, verifier = _sandbox_inputs(tmp_path)
    telemetry = OperationalTelemetryHub(
        database_path=tmp_path / "disabled.sqlite3",
        enabled=False,
    )
    engine = PassiveSandboxEngineV2(
        control=SandboxEngineControl(),
        verifier=verifier,
        telemetry_hub=telemetry,
    )
    assert (
        engine.simulate(
            request=request,
            gateway=gateway,
            grant=grant,
            evidence=evidence,
        )
        is None
    )
    assert not (tmp_path / "disabled.sqlite3").exists()
