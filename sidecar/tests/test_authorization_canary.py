"""Characterization tests for the non-authoritative grant canary."""

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from sentinel.authorization_canary import (
    AuthorizationCanaryService,
    CanaryAuditEvent,
    authorization_canary_enabled,
)
from sentinel.contracts import (
    AuthorizationGrantV1,
    ExecutionPlanV2,
    ExecutionStepV2,
    IdentityContextV1,
    PolicyDecisionV2,
    PolicyDecisionValueV2,
)


def _step(
    *,
    step_id: str = "launch",
    parameters=None,
) -> ExecutionStepV2:
    return ExecutionStepV2(
        schema_version="2.0",
        step_id=step_id,
        tool_id="executor.launch",
        parameters=parameters or {"application_id": "win32.notepad"},
    )


def _plan(
    *,
    plan_id: str = "plan_notepad",
    step: ExecutionStepV2 | None = None,
) -> ExecutionPlanV2:
    selected = step or _step()
    return ExecutionPlanV2(
        schema_version="2.0",
        plan_id=plan_id,
        intent_id="intent_notepad",
        steps=(selected,),
        params_hash=ExecutionPlanV2.calculate_params_hash(
            intent_id="intent_notepad",
            steps=(selected,),
        ),
    )


def _identity(
    *,
    user_id: str = "local-user",
    session_id: str = "session-one",
) -> IdentityContextV1:
    return IdentityContextV1.create(
        user_id=user_id,
        session_id=session_id,
        roles=("user",),
        authentication_method="local",
        created_at=datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc),
    )


def _decision(
    *,
    plan_id: str = "plan_notepad",
) -> PolicyDecisionV2:
    return PolicyDecisionV2(
        schema_version="2.0",
        decision_id="decision_allow_notepad",
        plan_id=plan_id,
        decision=PolicyDecisionValueV2.ALLOW,
        policy_ids=("application.launch",),
        reason="Shadow canary allow",
        risk_context={"risk": "medium"},
        timestamp=datetime.now(timezone.utc),
    )


def _grant(
    service: AuthorizationCanaryService,
    *,
    now: datetime | None = None,
) -> tuple[
    AuthorizationGrantV1,
    PolicyDecisionV2,
    IdentityContextV1,
    ExecutionPlanV2,
    ExecutionStepV2,
]:
    step = _step()
    plan = _plan(step=step)
    identity = _identity()
    decision = _decision()
    grant = service.create_grant(
        policy_decision=decision,
        identity=identity,
        plan=plan,
        step=step,
        now=now,
    )
    assert grant is not None
    return grant, decision, identity, plan, step


def test_canary_disabled_default(monkeypatch):
    monkeypatch.delenv("AUTHORIZATION_CANARY_ENABLED", raising=False)
    assert authorization_canary_enabled() is False
    service = AuthorizationCanaryService()
    assert service.enabled is False
    assert (
        service.create_grant(
            policy_decision=_decision(),
            identity=_identity(),
            plan=_plan(),
            step=_step(),
        )
        is None
    )


def test_canary_creates_grant():
    service = AuthorizationCanaryService(enabled=True)
    grant, decision, identity, plan, step = _grant(service)

    assert grant.policy_decision_id == decision.decision_id
    assert grant.plan_id == plan.plan_id
    assert grant.identity_context == identity
    assert grant.authorized_steps[0].step_id == step.step_id
    assert grant.nonce
    assert grant.single_use is True
    service.validate(
        grant,
        policy_decision=decision,
        identity=identity,
        plan=plan,
        step=step,
    )
    assert service.audit.records()[0].event_type == CanaryAuditEvent.GRANT_CREATED.value


def test_grant_requires_policy_decision():
    service = AuthorizationCanaryService(enabled=True)
    with pytest.raises(ValueError, match="policy_decision"):
        service.create_grant(
            policy_decision=None,
            identity=_identity(),
            plan=_plan(),
            step=_step(),
        )


def test_grant_requires_identity():
    service = AuthorizationCanaryService(enabled=True)
    with pytest.raises(ValueError, match="identity"):
        service.create_grant(
            policy_decision=_decision(),
            identity=None,
            plan=_plan(),
            step=_step(),
        )


def test_grant_detects_parameter_change():
    service = AuthorizationCanaryService(enabled=True)
    grant, decision, identity, _plan_original, _step_original = _grant(service)
    modified_step = _step(parameters={"application_id": "other.app"})
    modified_plan = _plan(step=modified_step)

    with pytest.raises(ValueError, match="parameter_hash_mismatch"):
        service.validate(
            grant,
            policy_decision=decision,
            identity=identity,
            plan=modified_plan,
            step=modified_step,
        )


def test_grant_detects_plan_change():
    service = AuthorizationCanaryService(enabled=True)
    grant, decision, identity, _plan_original, step = _grant(service)
    changed_plan = _plan(plan_id="plan_other", step=step)

    with pytest.raises(ValueError, match="policy_plan_mismatch"):
        service.validate(
            grant,
            policy_decision=decision,
            identity=identity,
            plan=changed_plan,
            step=step,
        )


def test_grant_expiration():
    service = AuthorizationCanaryService(
        enabled=True,
        ttl=timedelta(seconds=30),
    )
    now = datetime.now(timezone.utc)
    grant, decision, identity, plan, step = _grant(service, now=now)

    with pytest.raises(PermissionError, match="expired"):
        service.validate(
            grant,
            policy_decision=decision,
            identity=identity,
            plan=plan,
            step=step,
            at=now + timedelta(seconds=31),
        )


def test_grant_single_use():
    service = AuthorizationCanaryService(enabled=True)
    grant, decision, identity, plan, step = _grant(service)
    service.validate(
        grant,
        policy_decision=decision,
        identity=identity,
        plan=plan,
        step=step,
    )
    consumed = service.consume_simulation(
        grant,
        at=grant.created_at + timedelta(seconds=1),
    )
    assert consumed.consumed_at is not None
    with pytest.raises(PermissionError, match="grant_replay"):
        service.consume_simulation(
            grant,
            at=grant.created_at + timedelta(seconds=2),
        )
    assert service.audit.records()[-2].event_type == CanaryAuditEvent.GRANT_CONSUMED_SIMULATION.value


def test_grant_never_executes_tool():
    assert _forbidden_calls({"execute", "launch", "run", "popen", "start"}) == []


def test_canary_no_runtime_dependency():
    forbidden = {
        "sentinel.core.tool_gateway",
        "sentinel.core.policy_engine",
        "sentinel.core.decision_engine",
        "sentinel.core.orchestrator",
        "sidecar.services.executor_service",
    }
    violations = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            modules = ()
            if isinstance(node, ast.Import):
                modules = tuple(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = (node.module,)
            for module in modules:
                if any(module == item or module.startswith(f"{item}.") for item in forbidden):
                    violations.append((path.name, module))
    assert violations == []


def test_grant_rejects_different_identity_and_step():
    service = AuthorizationCanaryService(enabled=True)
    grant, decision, _identity_original, plan, step = _grant(service)
    with pytest.raises(ValueError, match="identity_mismatch"):
        service.validate(
            grant,
            policy_decision=decision,
            identity=_identity(session_id="session-other"),
            plan=plan,
            step=step,
        )
    with pytest.raises(ValueError, match="step_mismatch"):
        service.validate(
            grant,
            policy_decision=decision,
            identity=_identity(),
            plan=plan,
            step=_step(step_id="different"),
        )


def _trees():
    for path in Path("sentinel/authorization_canary").glob("*.py"):
        yield path, ast.parse(path.read_text(encoding="utf-8"))


def _forbidden_calls(names: set[str]):
    lowered = {name.casefold() for name in names}
    violations = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
            if called.casefold() in lowered:
                violations.append((path.name, node.lineno, called))
    return violations
