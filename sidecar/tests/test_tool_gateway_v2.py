from datetime import timedelta

import pytest
from pydantic import ValidationError

from sentinel.authorization_manager import (
    AuthorizationManagerControl,
    AuthorizationManagerV2,
)
from sentinel.contracts import (
    AuthorizationScopeV1,
    ConsentDecisionValueV1,
    EvidenceIntegrityStatusV1,
    SimulationRiskLevelV1,
    ToolCategoryV1,
    ToolGatewayDecisionValueV1,
)
from sentinel.operational_telemetry_hub import OperationalTelemetryHub
from sentinel.tool_gateway import (
    PassiveToolGatewayV2,
    ToolGatewayControl,
    ToolRequestV1,
)
from sentinel.tool_gateway.catalog import canonical_parameters_hash
from test_authorization_manager_v2 import _granted_inputs


def _inputs(tmp_path, *, scope=AuthorizationScopeV1.READ_ONLY):
    values, policy, consent, verifier = _granted_inputs(tmp_path)
    authorization_telemetry = OperationalTelemetryHub(
        database_path=tmp_path / "authorization-source.sqlite3",
        enabled=True,
    )
    authorization = AuthorizationManagerV2(
        control=AuthorizationManagerControl(enabled=True),
        verifier=verifier,
        telemetry_hub=authorization_telemetry,
    )
    now = consent.timestamp + timedelta(minutes=1)
    is_change = scope is AuthorizationScopeV1.USER_APPROVED_ACTION
    tool_id = "sentinel.application.launch" if is_change else "sentinel.file.metadata"
    category = ToolCategoryV1.APPLICATION_LAUNCH if is_change else ToolCategoryV1.FILE_READ
    parameters = ({"name": "application_id", "value": "app.verified"},) if is_change else ()
    parameter_values = {item["name"]: item["value"] for item in parameters}
    params_hash = canonical_parameters_hash(parameter_values)
    pending = authorization.request(
        consent=consent,
        policy=policy,
        evidence=values["evidence"],
        scope=scope,
        expires_at=now + timedelta(minutes=3),
        params_hash=params_hash,
        plan_id="plan:gateway-test",
        step_id="step:gateway-test",
        tool_id=tool_id,
        now=now,
    ).grant
    grant = authorization.authorize_limited(
        pending.grant_id,
        actor="human:reviewer",
        now=now + timedelta(seconds=1),
    ).grant
    authorization_telemetry.close()
    request = ToolRequestV1(
        request_id="tool-request:one",
        correlation_id=grant.correlation_id,
        evidence_hash=grant.evidence_hash,
        issuer_id=grant.issuer_id,
        authorization_reference=grant.grant_id,
        plan_id=grant.plan_id,
        step_id=grant.authorized_steps[0].step_id,
        tool_id=tool_id,
        tool_version="1.0.0",
        requested_tool_category=category,
        requested_scope=scope,
        parameters=parameters,
        params_hash=params_hash,
        timestamp=now + timedelta(seconds=2),
    )
    return request, grant, consent, values["evidence"], policy, verifier


def _gateway(tmp_path, verifier, *, enabled=True):
    telemetry = OperationalTelemetryHub(
        database_path=tmp_path / "gateway.sqlite3",
        enabled=True,
    )
    gateway = PassiveToolGatewayV2(
        control=ToolGatewayControl(enabled=enabled),
        verifier=verifier,
        telemetry_hub=telemetry,
    )
    return gateway, telemetry


def test_deterministic_allowed_decision_is_still_non_authoritative(tmp_path):
    request, grant, consent, evidence, policy, verifier = _inputs(tmp_path)
    gateway, telemetry = _gateway(tmp_path, verifier)
    try:
        kwargs = {
            "request": request,
            "grant": grant,
            "consent": consent,
            "evidence": evidence,
            "policy": policy,
            "now": request.timestamp,
        }
        first = gateway.evaluate(**kwargs)
        second = gateway.evaluate(**kwargs)
        assert first.decision == second.decision
        assert first.decision.decision is (ToolGatewayDecisionValueV1.TOOL_ALLOWED)
        assert first.decision.authority is False
        assert first.decision.execution_requested is False
        assert len(telemetry.timeline.latest()) == 1
    finally:
        telemetry.close()


def test_expired_grant_and_revoked_consent_are_blocked(tmp_path):
    request, grant, consent, evidence, policy, verifier = _inputs(tmp_path)
    gateway, telemetry = _gateway(tmp_path, verifier)
    try:
        expired = gateway.evaluate(
            request=request,
            grant=grant,
            consent=consent,
            evidence=evidence,
            policy=policy,
            now=grant.expires_at + timedelta(seconds=1),
        )
        assert expired.decision.decision is (ToolGatewayDecisionValueV1.TOOL_BLOCKED)
        assert "AUTHORIZATION_EXPIRED" in expired.reason_codes

        revoked = consent.__class__.model_validate(
            {
                **consent.model_dump(),
                "decision": ConsentDecisionValueV1.CONSENT_REVOKED,
                "revoked": True,
                "timestamp": consent.timestamp + timedelta(seconds=1),
            }
        )
        revoked_result = gateway.evaluate(
            request=request.model_copy(update={"request_id": "tool-request:two"}),
            grant=grant,
            consent=revoked,
            evidence=evidence,
            policy=policy,
            now=request.timestamp,
        )
        assert revoked_result.decision.decision is (ToolGatewayDecisionValueV1.TOOL_BLOCKED)
        assert "CONSENT_NOT_GRANTED" in revoked_result.reason_codes
    finally:
        telemetry.close()


def test_scope_escalation_and_category_outside_scope_are_blocked(tmp_path):
    request, grant, consent, evidence, policy, verifier = _inputs(
        tmp_path,
        scope=AuthorizationScopeV1.SIMULATION_ONLY,
    )
    gateway, telemetry = _gateway(tmp_path, verifier)
    try:
        escalated = request.model_copy(update={"requested_scope": AuthorizationScopeV1.READ_ONLY})
        result = gateway.evaluate(
            request=escalated,
            grant=grant,
            consent=consent,
            evidence=evidence,
            policy=policy,
            now=request.timestamp,
        )
        assert "SCOPE_ESCALATION" in result.reason_codes

        outside = request.model_copy(
            update={
                "request_id": "tool-request:outside",
                "requested_tool_category": ToolCategoryV1.PROCESS_INFORMATION,
            }
        )
        result = gateway.evaluate(
            request=outside,
            grant=grant,
            consent=consent,
            evidence=evidence,
            policy=policy,
            now=request.timestamp,
        )
        assert "TOOL_CATEGORY_MISMATCH" in result.reason_codes

        tampered_grant = grant.model_copy(update={"scope": AuthorizationScopeV1.READ_ONLY})
        tampered = gateway.evaluate(
            request=request.model_copy(update={"request_id": "tool-request:tampered"}),
            grant=tampered_grant,
            consent=consent,
            evidence=evidence,
            policy=policy,
            now=request.timestamp,
        )
        assert "AUTHORIZATION_INTEGRITY_INVALID" in tampered.reason_codes
    finally:
        telemetry.close()


def test_invalid_evidence_unknown_issuer_and_provenance_mismatch_are_blocked(
    tmp_path,
):
    request, grant, consent, evidence, policy, verifier = _inputs(tmp_path)
    gateway, telemetry = _gateway(tmp_path, verifier)
    try:
        invalid = evidence.model_copy(update={"integrity_status": EvidenceIntegrityStatusV1.INVALID})
        invalid_result = gateway.evaluate(
            request=request,
            grant=grant,
            consent=consent,
            evidence=invalid,
            policy=policy,
            now=request.timestamp,
        )
        assert invalid_result.decision.decision is (ToolGatewayDecisionValueV1.TOOL_BLOCKED)
        assert "EVIDENCE_NOT_VERIFIED" in invalid_result.reason_codes

        unknown = evidence.model_copy(update={"issuer_id": "unknown.issuer"})
        unknown_result = gateway.evaluate(
            request=request.model_copy(update={"request_id": "tool-request:u"}),
            grant=grant,
            consent=consent,
            evidence=unknown,
            policy=policy,
            now=request.timestamp,
        )
        assert "EVIDENCE_UNKNOWN_ISSUER" in unknown_result.reason_codes

        mismatch = request.model_copy(
            update={
                "request_id": "tool-request:m",
                "correlation_id": "decision:different",
                "evidence_hash": "b" * 64,
            }
        )
        mismatch_result = gateway.evaluate(
            request=mismatch,
            grant=grant,
            consent=consent,
            evidence=evidence,
            policy=policy,
            now=request.timestamp,
        )
        assert "CORRELATION_MISMATCH" in mismatch_result.reason_codes
        assert "EVIDENCE_HASH_MISMATCH" in mismatch_result.reason_codes
        assert mismatch_result.metrics.invalid_origin >= 1
    finally:
        telemetry.close()


def test_critical_risk_blocks_and_catalog_application_can_pass(tmp_path):
    request, grant, consent, evidence, policy, verifier = _inputs(
        tmp_path,
        scope=AuthorizationScopeV1.USER_APPROVED_ACTION,
    )
    gateway, telemetry = _gateway(tmp_path, verifier)
    try:
        critical_policy = policy.model_copy(update={"risk_level": SimulationRiskLevelV1.CRITICAL})
        critical = gateway.evaluate(
            request=request,
            grant=grant,
            consent=consent,
            evidence=evidence,
            policy=critical_policy,
            now=request.timestamp,
        )
        assert critical.decision.decision is (ToolGatewayDecisionValueV1.TOOL_BLOCKED)

        change_request = request.model_copy(update={"request_id": "tool-request:change"})
        review = gateway.evaluate(
            request=change_request,
            grant=grant,
            consent=consent,
            evidence=evidence,
            policy=policy,
            now=request.timestamp,
        )
        assert review.decision.decision is ToolGatewayDecisionValueV1.TOOL_ALLOWED
    finally:
        telemetry.close()


def test_request_rejects_paths_commands_arguments_and_payloads():
    base = {
        "request_id": "tool-request:safe",
        "correlation_id": "decision:safe",
        "evidence_hash": "a" * 64,
        "issuer_id": "issuer",
        "authorization_reference": "grant:safe",
        "plan_id": "plan:safe",
        "step_id": "step:safe",
        "tool_id": "sentinel.file.metadata",
        "tool_version": "1.0.0",
        "requested_tool_category": "FILE_READ",
        "requested_scope": "READ_ONLY",
        "parameters": (),
        "params_hash": "a" * 64,
        "timestamp": "2026-01-01T00:00:00Z",
    }
    for field in ("path", "command", "arguments", "payload", "script"):
        with pytest.raises(ValidationError):
            ToolRequestV1.model_validate({**base, field: "forbidden"})


def test_gateway_writes_audit_event_timeline_and_metric_snapshot(tmp_path):
    request, grant, consent, evidence, policy, verifier = _inputs(tmp_path)
    gateway, telemetry = _gateway(tmp_path, verifier)
    try:
        result = gateway.evaluate(
            request=request,
            grant=grant,
            consent=consent,
            evidence=evidence,
            policy=policy,
            now=request.timestamp,
        )
        assert result.audit_event.result == result.decision.decision.value
        assert telemetry.timeline.latest() == (result.operational_event,)
        assert result.telemetry_snapshot is not None
    finally:
        telemetry.close()


def test_gateway_is_disabled_by_default(tmp_path):
    request, grant, consent, evidence, policy, verifier = _inputs(tmp_path)
    telemetry = OperationalTelemetryHub(
        database_path=tmp_path / "disabled.sqlite3",
        enabled=False,
    )
    gateway = PassiveToolGatewayV2(
        control=ToolGatewayControl(environ={}),
        verifier=verifier,
        telemetry_hub=telemetry,
    )
    assert (
        gateway.evaluate(
            request=request,
            grant=grant,
            consent=consent,
            evidence=evidence,
            policy=policy,
            now=request.timestamp,
        )
        is None
    )
    assert not (tmp_path / "disabled.sqlite3").exists()
