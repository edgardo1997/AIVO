from datetime import timedelta

import pytest
from pydantic import ValidationError

from sentinel.contracts import (
    AuthorizationScopeV1,
    ExecutionPlanStatusV1,
    PolicyEvaluationStatusV1,
)
from sentinel.execution_boundary import (
    ExecutionBoundaryControl,
    PassiveExecutionBoundaryV2,
)
from sentinel.execution_planner import (
    ExecutionPlannerControl,
    PassiveExecutionPlannerV2,
    PlannerRequestV1,
)
from sentinel.operational_telemetry_hub import OperationalTelemetryHub
from test_execution_boundary_v2 import _boundary_inputs


def _planner_inputs(tmp_path):
    request, grant, gateway, sandbox, policy, evidence, verifier = _boundary_inputs(tmp_path)
    boundary_hub = OperationalTelemetryHub(
        database_path=tmp_path / "planner-boundary.sqlite3",
        enabled=True,
    )
    boundary = (
        PassiveExecutionBoundaryV2(
            control=ExecutionBoundaryControl(enabled=True),
            verifier=verifier,
            telemetry_hub=boundary_hub,
        )
        .evaluate(
            request=request,
            grant=grant,
            gateway=gateway,
            simulation=sandbox,
            policy=policy,
            evidence=evidence,
        )
        .decision
    )
    boundary_hub.close()
    planner_request = PlannerRequestV1(
        request_id="planner-request:one",
        correlation_id=boundary.correlation_id,
        evidence_hash=boundary.evidence_hash,
        issuer_id=boundary.issuer_id,
        authorization_reference=grant.grant_id,
        boundary_reference=boundary.decision_id,
        simulation_reference=sandbox.simulation_id,
        policy_reference=policy.policy_id,
        action_category=boundary.action_category,
        scope=boundary.scope,
        timestamp=boundary.timestamp + timedelta(seconds=1),
    )
    return planner_request, boundary, grant, sandbox, policy, evidence, verifier


def _engine(tmp_path, verifier, *, enabled=True):
    telemetry = OperationalTelemetryHub(
        database_path=tmp_path / "execution-planner.sqlite3",
        enabled=True,
    )
    engine = PassiveExecutionPlannerV2(
        control=ExecutionPlannerControl(enabled=enabled),
        verifier=verifier,
        telemetry_hub=telemetry,
    )
    return engine, telemetry


def test_plan_is_deterministic_descriptive_and_non_authoritative(tmp_path):
    request, boundary, grant, sandbox, policy, evidence, verifier = _planner_inputs(tmp_path)
    engine, telemetry = _engine(tmp_path, verifier)
    try:
        kwargs = {
            "request": request,
            "boundary": boundary,
            "grant": grant,
            "sandbox": sandbox,
            "policy": policy,
            "evidence": evidence,
        }
        first = engine.create_plan(**kwargs)
        second = engine.create_plan(**kwargs)
        assert first.plan == second.plan
        assert first.plan.status is ExecutionPlanStatusV1.PLAN_REVIEW_REQUIRED
        assert len(first.plan.steps) == 5
        assert first.plan.authority is False
        assert first.plan.execution_requested is False
        assert len(telemetry.timeline.latest()) == 1
    finally:
        telemetry.close()


def test_disabled_by_default_produces_nothing(tmp_path):
    values = _planner_inputs(tmp_path)
    request, boundary, grant, sandbox, policy, evidence, verifier = values
    engine, telemetry = _engine(tmp_path, verifier, enabled=False)
    try:
        assert (
            engine.create_plan(
                request=request,
                boundary=boundary,
                grant=grant,
                sandbox=sandbox,
                policy=policy,
                evidence=evidence,
            )
            is None
        )
        assert telemetry.timeline.latest() == ()
    finally:
        telemetry.close()


def test_scope_escalation_and_origin_mismatch_are_invalid(tmp_path):
    values = _planner_inputs(tmp_path)
    request, boundary, grant, sandbox, policy, evidence, verifier = values
    engine, telemetry = _engine(tmp_path, verifier)
    try:
        altered = request.model_copy(
            update={
                "scope": AuthorizationScopeV1.USER_APPROVED_ACTION,
                "correlation_id": "decision:other",
            }
        )
        result = engine.create_plan(
            request=altered,
            boundary=boundary,
            grant=grant,
            sandbox=sandbox,
            policy=policy,
            evidence=evidence,
        )
        assert result.plan.status is ExecutionPlanStatusV1.PLAN_INVALID
        assert "SCOPE_ESCALATION" in result.validation_errors
        assert "CORRELATION_MISMATCH" in result.validation_errors
    finally:
        telemetry.close()


def test_expired_or_revoked_grant_is_invalid(tmp_path):
    values = _planner_inputs(tmp_path)
    request, boundary, grant, sandbox, policy, evidence, verifier = values
    engine, telemetry = _engine(tmp_path, verifier)
    try:
        late = request.model_copy(update={"timestamp": grant.expires_at + timedelta(seconds=1)})
        revoked = grant.model_copy(update={"revoked": True})
        result = engine.create_plan(
            request=late,
            boundary=boundary,
            grant=revoked,
            sandbox=sandbox,
            policy=policy,
            evidence=evidence,
        )
        assert "AUTHORIZATION_EXPIRED" in result.validation_errors
        assert "AUTHORIZATION_REVOKED" in result.validation_errors
    finally:
        telemetry.close()


def test_blocking_policy_blocks_plan(tmp_path):
    values = _planner_inputs(tmp_path)
    request, boundary, grant, sandbox, policy, evidence, verifier = values
    engine, telemetry = _engine(tmp_path, verifier)
    try:
        blocked = policy.model_copy(update={"policy_status": PolicyEvaluationStatusV1.POLICY_BLOCKED})
        result = engine.create_plan(
            request=request,
            boundary=boundary,
            grant=grant,
            sandbox=sandbox,
            policy=blocked,
            evidence=evidence,
        )
        assert result.plan.status is ExecutionPlanStatusV1.PLAN_BLOCKED
    finally:
        telemetry.close()


def test_request_rejects_executable_content(tmp_path):
    request, *_ = _planner_inputs(tmp_path)
    for field, value in (
        ("command", "remove item"),
        ("path", "C:\\private"),
        ("script", "unsafe"),
        ("arguments", ("--force",)),
        ("secret", "credential"),
    ):
        with pytest.raises(ValidationError):
            PlannerRequestV1(**request.model_dump(), **{field: value})


def test_plan_and_steps_are_immutable(tmp_path):
    values = _planner_inputs(tmp_path)
    request, boundary, grant, sandbox, policy, evidence, verifier = values
    engine, telemetry = _engine(tmp_path, verifier)
    try:
        plan = engine.create_plan(
            request=request,
            boundary=boundary,
            grant=grant,
            sandbox=sandbox,
            policy=policy,
            evidence=evidence,
        ).plan
        with pytest.raises(ValidationError):
            plan.authority = True
        with pytest.raises(ValidationError):
            plan.steps[0].description = "changed"
    finally:
        telemetry.close()
