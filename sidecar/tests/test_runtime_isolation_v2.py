from datetime import timedelta

import pytest
from pydantic import ValidationError

from sentinel.contracts import (
    AuthorizationScopeV1,
    IsolationStatusV1,
    SandboxExecutionStatusV1,
)
from sentinel.executor_sandbox import (
    ExecutorSandboxControl,
    PassiveExecutorSandboxV2,
)
from sentinel.operational_telemetry_hub import OperationalTelemetryHub
from sentinel.runtime_isolation import (
    IsolationRequestV1,
    PassiveRuntimeIsolationV2,
    RuntimeIsolationControl,
)
from test_executor_sandbox_v2 import _execution_inputs


def _isolation_inputs(tmp_path):
    request, plan, grant, policy, evidence, verifier = _execution_inputs(tmp_path)
    execution_hub = OperationalTelemetryHub(
        database_path=tmp_path / "isolation-execution.sqlite3",
        enabled=True,
    )
    execution = (
        PassiveExecutorSandboxV2(
            control=ExecutorSandboxControl(enabled=True),
            verifier=verifier,
            telemetry_hub=execution_hub,
        )
        .simulate(
            request=request,
            plan=plan,
            grant=grant,
            policy=policy,
            evidence=evidence,
        )
        .result
    )
    execution_hub.close()
    isolation_request = IsolationRequestV1(
        request_id="isolation-request:one",
        execution_reference=execution.execution_id,
        plan_reference=plan.plan_id,
        authorization_reference=grant.grant_id,
        correlation_id=execution.correlation_id,
        evidence_hash=execution.evidence_hash,
        issuer_id=execution.issuer_id,
        requested_scope=grant.scope,
        timestamp=execution.timestamp + timedelta(seconds=1),
    )
    return isolation_request, execution, plan, grant, evidence, verifier


def _engine(tmp_path, verifier, *, enabled=True):
    telemetry = OperationalTelemetryHub(
        database_path=tmp_path / "runtime-isolation.sqlite3",
        enabled=True,
    )
    engine = PassiveRuntimeIsolationV2(
        control=RuntimeIsolationControl(enabled=enabled),
        verifier=verifier,
        telemetry_hub=telemetry,
    )
    return engine, telemetry


def test_context_is_deterministic_idempotent_and_descriptive(tmp_path):
    request, execution, plan, grant, evidence, verifier = _isolation_inputs(tmp_path)
    engine, telemetry = _engine(tmp_path, verifier)
    try:
        kwargs = {
            "request": request,
            "execution": execution,
            "plan": plan,
            "grant": grant,
            "evidence": evidence,
        }
        first = engine.evaluate(**kwargs)
        second = engine.evaluate(**kwargs)
        assert first.context == second.context
        assert first.context.status is IsolationStatusV1.ISOLATION_READY
        assert first.context.allowed_capabilities == (
            "filesystem_read",
            "simulation",
            "telemetry",
        )
        assert "execute_command" in first.context.blocked_capabilities
        assert first.context.resource_limits.system_access is False
        assert first.context.resource_limits.network_access is False
        assert first.context.authority is False
        assert first.context.execution_requested is False
        assert len(telemetry.timeline.latest()) == 1
    finally:
        telemetry.close()


def test_disabled_by_default_produces_nothing(tmp_path):
    request, execution, plan, grant, evidence, verifier = _isolation_inputs(tmp_path)
    engine, telemetry = _engine(tmp_path, verifier, enabled=False)
    try:
        assert (
            engine.evaluate(
                request=request,
                execution=execution,
                plan=plan,
                grant=grant,
                evidence=evidence,
            )
            is None
        )
        assert telemetry.timeline.latest() == ()
    finally:
        telemetry.close()


def test_invalid_evidence_identity_and_scope_are_invalid(tmp_path):
    request, execution, plan, grant, evidence, verifier = _isolation_inputs(tmp_path)
    engine, telemetry = _engine(tmp_path, verifier)
    try:
        altered = request.model_copy(
            update={
                "issuer_id": "unknown:issuer",
                "requested_scope": AuthorizationScopeV1.USER_APPROVED_ACTION,
            }
        )
        result = engine.evaluate(
            request=altered,
            execution=execution,
            plan=plan,
            grant=grant,
            evidence=evidence.model_copy(update={"signature": "invalid"}),
        )
        assert result.context.status is IsolationStatusV1.ISOLATION_INVALID
        assert "IDENTITY_OR_ISSUER_UNKNOWN" in result.validation_errors
        assert "SCOPE_ESCALATION" in result.validation_errors
        assert any(item.startswith("EVIDENCE_") for item in result.validation_errors)
        assert result.context.allowed_capabilities == ()
    finally:
        telemetry.close()


def test_inconsistent_plan_is_invalid(tmp_path):
    request, execution, plan, grant, evidence, verifier = _isolation_inputs(tmp_path)
    engine, telemetry = _engine(tmp_path, verifier)
    try:
        altered = request.model_copy(update={"plan_reference": "plan-result:other"})
        result = engine.evaluate(
            request=altered,
            execution=execution,
            plan=plan,
            grant=grant,
            evidence=evidence,
        )
        assert "PLAN_INCONSISTENT" in result.validation_errors
    finally:
        telemetry.close()


def test_blocked_sandbox_blocks_isolation(tmp_path):
    request, execution, plan, grant, evidence, verifier = _isolation_inputs(tmp_path)
    engine, telemetry = _engine(tmp_path, verifier)
    try:
        blocked = execution.model_copy(update={"final_state": SandboxExecutionStatusV1.SANDBOX_BLOCKED})
        result = engine.evaluate(
            request=request,
            execution=blocked,
            plan=plan,
            grant=grant,
            evidence=evidence,
        )
        assert result.context.status is IsolationStatusV1.ISOLATION_BLOCKED
    finally:
        telemetry.close()


def test_request_rejects_os_and_executable_fields(tmp_path):
    request, *_ = _isolation_inputs(tmp_path)
    for field, value in (
        ("command", "unsafe"),
        ("path", "C:\\private"),
        ("process", "real"),
        ("container", "real"),
        ("payload", {"secret": "x"}),
    ):
        with pytest.raises(ValidationError):
            IsolationRequestV1(**request.model_dump(), **{field: value})


def test_context_is_immutable(tmp_path):
    request, execution, plan, grant, evidence, verifier = _isolation_inputs(tmp_path)
    engine, telemetry = _engine(tmp_path, verifier)
    try:
        context = engine.evaluate(
            request=request,
            execution=execution,
            plan=plan,
            grant=grant,
            evidence=evidence,
        ).context
        with pytest.raises(ValidationError):
            context.authority = True
    finally:
        telemetry.close()
