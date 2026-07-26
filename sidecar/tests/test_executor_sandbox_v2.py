from datetime import timedelta

import pytest
from pydantic import ValidationError

from sentinel.contracts import (
    AuthorizationScopeV1,
    ExecutionPlanStatusV1,
    PolicyEvaluationStatusV1,
    SandboxExecutionStatusV1,
)
from sentinel.execution_planner import (
    ExecutionPlannerControl,
    PassiveExecutionPlannerV2,
)
from sentinel.executor_sandbox import (
    ExecutorSandboxControl,
    PassiveExecutorSandboxV2,
    SandboxExecutionRequestV1,
)
from sentinel.operational_telemetry_hub import OperationalTelemetryHub
from test_execution_planner_v2 import _planner_inputs


def _execution_inputs(tmp_path):
    request, boundary, grant, sandbox, policy, evidence, verifier = _planner_inputs(tmp_path)
    planner_hub = OperationalTelemetryHub(
        database_path=tmp_path / "executor-planner.sqlite3",
        enabled=True,
    )
    plan = (
        PassiveExecutionPlannerV2(
            control=ExecutionPlannerControl(enabled=True),
            verifier=verifier,
            telemetry_hub=planner_hub,
        )
        .create_plan(
            request=request,
            boundary=boundary,
            grant=grant,
            sandbox=sandbox,
            policy=policy,
            evidence=evidence,
        )
        .plan
    )
    planner_hub.close()
    execution_request = SandboxExecutionRequestV1(
        request_id="sandbox-execution:one",
        plan_id=plan.plan_id,
        correlation_id=plan.correlation_id,
        evidence_hash=plan.evidence_hash,
        issuer_id=plan.issuer_id,
        authorization_reference=grant.grant_id,
        policy_reference=policy.policy_id,
        scope=grant.scope,
        timestamp=plan.timestamp + timedelta(seconds=1),
        valid_until=plan.timestamp + timedelta(minutes=1),
    )
    return execution_request, plan, grant, policy, evidence, verifier


def _engine(tmp_path, verifier, *, enabled=True):
    telemetry = OperationalTelemetryHub(
        database_path=tmp_path / "executor-sandbox.sqlite3",
        enabled=True,
    )
    engine = PassiveExecutorSandboxV2(
        control=ExecutorSandboxControl(enabled=enabled),
        verifier=verifier,
        telemetry_hub=telemetry,
    )
    return engine, telemetry


def test_simulation_is_deterministic_idempotent_and_passive(tmp_path):
    request, plan, grant, policy, evidence, verifier = _execution_inputs(tmp_path)
    engine, telemetry = _engine(tmp_path, verifier)
    try:
        kwargs = {
            "request": request,
            "plan": plan,
            "grant": grant,
            "policy": policy,
            "evidence": evidence,
        }
        first = engine.simulate(**kwargs)
        second = engine.simulate(**kwargs)
        assert first.result == second.result
        assert first.result.final_state is (SandboxExecutionStatusV1.SANDBOX_COMPLETED)
        assert first.result.completed_steps == len(plan.steps)
        assert first.result.failed_steps == 0
        assert first.result.rollback_available is True
        assert first.result.authority is False
        assert first.result.execution_requested is False
        assert len(telemetry.timeline.latest()) == 1
    finally:
        telemetry.close()


def test_disabled_by_default_does_nothing(tmp_path):
    request, plan, grant, policy, evidence, verifier = _execution_inputs(tmp_path)
    engine, telemetry = _engine(tmp_path, verifier, enabled=False)
    try:
        assert (
            engine.simulate(
                request=request,
                plan=plan,
                grant=grant,
                policy=policy,
                evidence=evidence,
            )
            is None
        )
        assert telemetry.timeline.latest() == ()
    finally:
        telemetry.close()


def test_invalid_evidence_and_hash_are_invalid(tmp_path):
    request, plan, grant, policy, evidence, verifier = _execution_inputs(tmp_path)
    engine, telemetry = _engine(tmp_path, verifier)
    try:
        altered = request.model_copy(update={"evidence_hash": "a" * 64})
        result = engine.simulate(
            request=altered,
            plan=plan,
            grant=grant,
            policy=policy,
            evidence=evidence.model_copy(update={"signature": "invalid"}),
        )
        assert result.result.final_state is (SandboxExecutionStatusV1.SANDBOX_INVALID)
        assert "EVIDENCE_HASH_MISMATCH" in result.validation_errors
        assert any(value.startswith("EVIDENCE_") for value in result.validation_errors)
    finally:
        telemetry.close()


def test_expired_plan_and_insufficient_scope_are_invalid(tmp_path):
    request, plan, grant, policy, evidence, verifier = _execution_inputs(tmp_path)
    engine, telemetry = _engine(tmp_path, verifier)
    try:
        expired = request.model_copy(
            update={
                "valid_until": request.timestamp - timedelta(seconds=1),
                "scope": AuthorizationScopeV1.USER_APPROVED_ACTION,
            }
        )
        result = engine.simulate(
            request=expired,
            plan=plan,
            grant=grant,
            policy=policy,
            evidence=evidence,
        )
        assert "PLAN_EXPIRED" in result.validation_errors
        assert "SCOPE_INSUFFICIENT" in result.validation_errors
    finally:
        telemetry.close()


def test_blocking_policy_or_plan_is_blocked(tmp_path):
    request, plan, grant, policy, evidence, verifier = _execution_inputs(tmp_path)
    engine, telemetry = _engine(tmp_path, verifier)
    try:
        blocked_plan = plan.model_copy(update={"status": ExecutionPlanStatusV1.PLAN_BLOCKED})
        blocked_policy = policy.model_copy(update={"policy_status": PolicyEvaluationStatusV1.POLICY_BLOCKED})
        result = engine.simulate(
            request=request,
            plan=blocked_plan,
            grant=grant,
            policy=blocked_policy,
            evidence=evidence,
        )
        assert result.result.final_state is (SandboxExecutionStatusV1.SANDBOX_BLOCKED)
        assert result.result.completed_steps == 0
    finally:
        telemetry.close()


def test_request_rejects_executable_fields(tmp_path):
    request, *_ = _execution_inputs(tmp_path)
    for field, value in (
        ("command", "unsafe"),
        ("path", "C:\\private"),
        ("script", "unsafe"),
        ("arguments", ("--force",)),
        ("payload", {"secret": "x"}),
    ):
        with pytest.raises(ValidationError):
            SandboxExecutionRequestV1(**request.model_dump(), **{field: value})


def test_result_and_steps_are_immutable(tmp_path):
    request, plan, grant, policy, evidence, verifier = _execution_inputs(tmp_path)
    engine, telemetry = _engine(tmp_path, verifier)
    try:
        result = engine.simulate(
            request=request,
            plan=plan,
            grant=grant,
            policy=policy,
            evidence=evidence,
        ).result
        with pytest.raises(ValidationError):
            result.authority = True
        with pytest.raises(ValidationError):
            result.simulated_steps[0].completed = False
    finally:
        telemetry.close()
