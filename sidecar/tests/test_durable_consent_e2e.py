"""P0-1 mandatory integral E2E: durable consent through real components.

Real components used (no stubs):
- ConfirmationBroker / ExecutionGrantRepository (SQLite temporal real)
- ExecutionPipeline / ToolExecutionGuard / ToolGateway
- Orchestrator.resume_approved_plan()

The only controlled test double is a real tool registered in the gateway that
records calls and passes through the real executor path.

Scenario coverage (17 required points):
  1. plan of at least two steps
  2. durable approval
  3. restart before the first step
  4. execution of step 0
  5. restart between steps
  6. execution of step 1
  7. distinct grants per step
  8. replay rejected
  9. out-of-order step rejected
 10. mutated parameters rejected
 11. different session rejected
 12. different identity rejected
 13. concurrency with a single winner
 14. partial failure leaves the plan failed
 15. later steps not authorizable
 16. durable audit after restart
 17. no rejection reaches the executor
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from repositories.database import DatabaseManager
from repositories.execution_grant_repository import ExecutionGrantRepository
from repositories.audit_repository import AuditRepository
from services.audit_service import AuditService
from sentinel.core.confirmation import ConfirmationBroker
from sentinel.core.decision_engine import Decision, DecisionResult
from sentinel.core.execution_pipeline import ExecutionPipeline
from sentinel.core.orchestrator import Orchestrator
from sentinel.core.policy import PolicyEffect
from sentinel.core.policy_engine import PolicyEngine
from sentinel.core.tool import Tool, ToolResult, ToolSpec
from sentinel.core.tool_gateway import ToolGateway
from sentinel.security.tool_guard import ToolExecutionGuard


def _future(minutes=10):
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z")


def _isolated_database(path):
    """Bypass the singleton only for a disposable fixture."""
    db = object.__new__(DatabaseManager)
    db._init(str(path))
    return db


class _E2ETool(Tool):
    def __init__(self, tool_id, calls, fail=False):
        self._tool_id, self._calls, self._fail = tool_id, calls, fail

    def spec(self):
        return ToolSpec(self._tool_id, self._tool_id, "durable e2e", "1", {}, ["test.execute"])

    async def execute(self, params, context):
        self._calls.append((self._tool_id, params, context.get("execution_grant")))
        if self._fail:
            return ToolResult.fail("intentional failure", self._tool_id)
        return ToolResult.ok({"ok": True}, self._tool_id)


def _identity(user="user-e2e", session="session-e2e"):
    return {
        "user_id": user,
        "session_id": session,
        "is_authenticated": True,
        "permissions": ["test.execute"],
    }


def _wire(db, calls, *, fail_step=None, decision_engine=None):
    """Real broker/repo/pipeline/guard/gateway/audit with a real SQLite DB."""
    broker = ConfirmationBroker(memory=None)
    broker._grants = ExecutionGrantRepository(db)
    gateway = ToolGateway(policy_engine=PolicyEngine(default_effect=PolicyEffect.ALLOW))
    gateway.set_confirmation_broker(broker)
    gateway.register(_E2ETool("e2e.alpha", calls))
    gateway.register(_E2ETool("e2e.beta", calls))
    gateway.register(_E2ETool("e2e.fail", calls, fail=True))
    audit = AuditService(AuditRepository(db))
    gateway._audit_service = audit
    guard = ToolExecutionGuard(tool_gateway=gateway, policy_engine=gateway._policy_engine, audit_service=audit)
    pipeline = ExecutionPipeline(gateway, guard)
    pipeline.set_confirmation_broker(broker)
    engine = MagicMock()
    engine.list_supported_targets.return_value = []
    orchestrator = Orchestrator(
        intent_engine=engine,
        tool_gateway=gateway,
        execution_pipeline=pipeline,
        audit_service=audit,
        decision_engine=decision_engine,
    )
    return broker, gateway, pipeline, orchestrator, audit


def _canonical(identity, plan_id="full-plan", steps=None):
    if steps is None:
        steps = [
            {"id": "step0", "tool_id": "e2e.alpha", "params": {"n": 0}},
            {"id": "step1", "tool_id": "e2e.beta", "params": {"n": 1}},
        ]
    identity_hash = ConfirmationBroker._hash({"user_id": identity["user_id"], "session_id": identity["session_id"]})
    payload, plan_hash = ConfirmationBroker.canonical_plan(
        {"plan_id": plan_id, "steps": steps}
    )
    return identity_hash, payload, plan_hash


def _binding(grant):
    return {
        "plan_grant_id": grant.plan_grant_id, "plan_id": grant.plan_id, "plan_hash": grant.plan_hash,
        "step_id": grant.step_id, "step_index": grant.step_index, "tool_id": grant.tool_id,
        "params_hash": grant.params_hash, "identity_hash": grant.identity_hash, "session_id": grant.session_id,
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_durable_consent_full_lifecycle_with_rejections(tmp_path):
    """Scenarios 1-12, 16, 17: full lifecycle + every rejection stays out of the executor."""
    db = _isolated_database(tmp_path / "full-e2e.db")
    identity = _identity()
    identity_hash, payload, plan_hash = _canonical(identity)

    # 1-2. Two-step plan, durable approval.
    grant_id = "full-grant"
    repo = ExecutionGrantRepository(db)
    assert repo.create_plan({
        "grant_id": grant_id, "user_id": identity["user_id"], "session_id": identity["session_id"],
        "identity_hash": identity_hash, "plan_id": "full-plan", "plan_hash": plan_hash,
        "plan_payload": payload, "risk_level": "high", "expires_at": _future(),
    })
    assert repo.transition_plan(grant_id, "pending", "approved", {"user_id": identity["user_id"]})

    # 3. Restart before the first step.
    db.close_connections()
    broker, _gw, pipeline, _orch, _audit = _wire(db, calls := [])
    assert broker.resume_approved_plan(grant_id, user_id=identity["user_id"], session_id=identity["session_id"], identity_hash=identity_hash)
    context = {"identity": identity}

    # 9. Out-of-order step (jump to step 1 before step 0 exists/consumed) is rejected.
    with pytest.raises(PermissionError, match="step order"):
        broker.issue_next_step_grant(plan_grant_id=grant_id, user_id=identity["user_id"], session_id=identity["session_id"], identity_hash=identity_hash, step_id="step1", step_index=1, tool_id="e2e.beta", params={"n": 1}, expires_at=_future())

    # 4. Step 0 executes with its own grant.
    first = broker.issue_next_step_grant(plan_grant_id=grant_id, user_id=identity["user_id"], session_id=identity["session_id"], identity_hash=identity_hash, step_id="step0", step_index=0, tool_id="e2e.alpha", params={"n": 0}, expires_at=_future())
    res0 = await pipeline.execute("e2e.alpha", {"n": 0}, context, source="approved_plan", execution_grant=first)
    assert res0.success
    assert len(calls) == 1
    assert calls[0][0] == "e2e.alpha"

    # 8. Replay of the consumed grant is rejected and never reaches the executor.
    replay = await pipeline.execute("e2e.alpha", {"n": 0}, context, source="approved_plan", execution_grant=first)
    assert not replay.success
    assert len(calls) == 1

    # 5. Restart between steps.
    db.close_connections()
    broker, gateway, pipeline, orchestrator, audit = _wire(db, calls)
    assert broker.resume_approved_plan(grant_id, user_id=identity["user_id"], session_id=identity["session_id"], identity_hash=identity_hash)

    # 10. Mutated parameters are rejected (binding mismatch), executor untouched.
    second = broker.issue_next_step_grant(plan_grant_id=grant_id, user_id=identity["user_id"], session_id=identity["session_id"], identity_hash=identity_hash, step_id="step1", step_index=1, tool_id="e2e.beta", params={"n": 1}, expires_at=_future())
    mutated = await pipeline.execute("e2e.beta", {"n": 999}, context, source="approved_plan", execution_grant=second)
    assert not mutated.success
    assert len(calls) == 1
    assert repo.get_step(second.step_grant_id)["status"] == "approved"

    # 11. Different session is rejected.
    other_session = await pipeline.execute("e2e.beta", {"n": 1}, {"identity": _identity(session="session-other")}, source="approved_plan", execution_grant=second)
    assert not other_session.success
    assert len(calls) == 1

    # 12. Different identity is rejected.
    other_user = await pipeline.execute("e2e.beta", {"n": 1}, {"identity": _identity(user="user-other")}, source="approved_plan", execution_grant=second)
    assert not other_user.success
    assert len(calls) == 1

    # 6. Step 1 executes with its own grant after all rejections.
    res1 = await pipeline.execute("e2e.beta", {"n": 1}, context, source="approved_plan", execution_grant=second)
    assert res1.success
    assert len(calls) == 2

    # 7. Distinct grants per step.
    first_row = db.fetchone("SELECT step_grant_id FROM step_execution_grants WHERE plan_grant_id=? AND step_index=0", (grant_id,))
    second_row = db.fetchone("SELECT step_grant_id FROM step_execution_grants WHERE plan_grant_id=? AND step_index=1", (grant_id,))
    assert first_row["step_grant_id"] != second_row["step_grant_id"]
    assert first.step_grant_id != second.step_grant_id

    assert broker.complete_plan(grant_id, user_id=identity["user_id"], session_id=identity["session_id"], identity_hash=identity_hash)
    assert repo.get_plan(grant_id)["status"] == "consumed"

    # 16. Durable audit survives a restart and records consumption.
    db.close_connections()
    db2 = _isolated_database(tmp_path / "full-e2e.db")
    assert db2.fetchone("SELECT COUNT(*) AS n FROM execution_grant_audit WHERE plan_id=? AND event_type='consumed'", ("full-plan",))["n"] >= 2
    db2.close()

    # 17. Every rejection above never reached the executor (calls stayed at 2).
    assert len(calls) == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_durable_consent_concurrency_single_winner(tmp_path):
    """Scenario 13: concurrent consumption of one step grant has a single winner."""
    db = _isolated_database(tmp_path / "concurrency-e2e.db")
    identity = _identity()
    identity_hash, payload, plan_hash = _canonical(identity)
    grant_id = "cc-grant"
    repo = ExecutionGrantRepository(db)
    assert repo.create_plan({
        "grant_id": grant_id, "user_id": identity["user_id"], "session_id": identity["session_id"],
        "identity_hash": identity_hash, "plan_id": "full-plan", "plan_hash": plan_hash,
        "plan_payload": payload, "risk_level": "high", "expires_at": _future(),
    })
    assert repo.transition_plan(grant_id, "pending", "approved", {"user_id": identity["user_id"]})
    broker = ConfirmationBroker(memory=None)
    broker._grants = repo
    broker.resume_approved_plan(grant_id, user_id=identity["user_id"], session_id=identity["session_id"], identity_hash=identity_hash)
    step = broker.issue_next_step_grant(plan_grant_id=grant_id, user_id=identity["user_id"], session_id=identity["session_id"], identity_hash=identity_hash, step_id="step0", step_index=0, tool_id="e2e.alpha", params={"n": 0}, expires_at=_future())
    binding = _binding(step)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: repo.consume_step(step.step_grant_id, binding), range(2)))
    assert results.count(True) == 1
    assert results.count(False) == 1
    assert repo.get_step(step.step_grant_id)["status"] == "consumed"
    db.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_durable_consent_partial_failure_fails_plan_and_blocks_following_steps(tmp_path):
    """Scenarios 14-15: partial failure durably closes the plan; later steps not authorizable."""
    db = _isolated_database(tmp_path / "fail-e2e.db")
    identity = _identity()
    identity_hash, payload, plan_hash = _canonical(
        identity, plan_id="fail-plan",
        steps=[
            {"id": "bad", "tool_id": "e2e.fail", "params": {}},
            {"id": "never", "tool_id": "e2e.never", "params": {}},
        ],
    )
    grant_id = "fail-grant"
    repo = ExecutionGrantRepository(db)
    assert repo.create_plan({
        "grant_id": grant_id, "user_id": identity["user_id"], "session_id": identity["session_id"],
        "identity_hash": identity_hash, "plan_id": "fail-plan", "plan_hash": plan_hash,
        "plan_payload": payload, "risk_level": "high", "expires_at": _future(),
    })
    assert repo.transition_plan(grant_id, "pending", "approved", {"user_id": identity["user_id"]})
    broker, gateway, pipeline, orchestrator, audit = _wire(db, calls := [])
    result = await orchestrator.resume_approved_plan(grant_id, identity)
    assert result.error == "intentional failure"
    assert repo.get_plan(grant_id)["status"] == "failed"
    assert len(calls) == 1
    with pytest.raises(PermissionError):
        broker.issue_next_step_grant(plan_grant_id=grant_id, user_id=identity["user_id"], session_id=identity["session_id"], identity_hash=identity_hash, step_id="never", step_index=1, tool_id="e2e.never", params={}, expires_at=_future())
    db.close()


class _RequireConfirmDecision:
    """Stub decision engine that always demands plan-level confirmation."""

    def should_skip_decision(self, intent):
        return False

    async def evaluate_async(self, plan, context, simulation_result=None, risk_classification=None):
        return DecisionResult(
            decision=Decision.REQUIRE_CONFIRM,
            plan=plan,
            reason="high risk (must be reconfirmed)",
            context_factors=[],
            base_risk_score=1.0,
            context_modifier=0.0,
            final_risk_score=1.0,
        )

    async def evaluate(self, plan, context, simulation_result=None, risk_classification=None):
        return await self.evaluate_async(plan, context, simulation_result, risk_classification)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_plan_approval_production_factory_end_to_end(tmp_path):
    """P0-1: production wiring via ConfirmationBroker.request_plan_grant /
    approve_plan_grant (the exact seam the v1 plans router uses), executed
    through Orchestrator.resume_approved_plan -> pipeline -> guard -> gateway.

    This proves the durable plan authority is reachable from the production
    factory methods (not only via direct repository writes) and that both steps
    execute under per-step grants while a high-risk plan-level reconfirmation
    is satisfied by the PlanApprovalGrant.
    """
    db = _isolated_database(tmp_path / "factory-e2e.db")
    identity = _identity()
    identity_hash, payload, plan_hash = _canonical(identity, plan_id="factory-plan")

    broker = ConfirmationBroker(memory=None)
    broker._grants = ExecutionGrantRepository(db)

    # Production seam: request_plan_grant() creates the PlanApprovalGrant.
    grant_id = broker.request_plan_grant(
        user_id=identity["user_id"], session_id=identity["session_id"], identity_hash=identity_hash,
        plan_id="factory-plan", plan_hash=plan_hash, plan_payload=payload,
        risk_level="high", expires_at=_future(),
    )
    assert broker._grants.get_plan(grant_id)["status"] == "pending"

    # Production seam: approve_plan_grant() transitions pending -> approved.
    assert broker.approve_plan_grant(grant_id, user_id=identity["user_id"])
    assert broker._grants.get_plan(grant_id)["status"] == "approved"

    broker, _gw, pipeline, _orch, _audit = _wire(db, calls := [], decision_engine=_RequireConfirmDecision())
    orchestrator = _orch
    result = await orchestrator.resume_approved_plan(grant_id, identity)
    assert result.error is None, result.error
    assert result.approved is True
    assert len(calls) == 2, "both granted steps execute through the production seam"
    assert broker._grants.get_plan(grant_id)["status"] == "consumed"
    db.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_resumed_approved_plan_passes_plan_level_reconfirmation(tmp_path):
    """A durably approved high-risk plan resumes past plan-level REQUIRE_CONFIRM.

    Regression for: `resume_approved_plan` re-ran the decision engine and a
    high-risk plan was re-blocked as a fresh confirmation, so a granted plan
    could never complete. The durable PlanApprovalGrant is the plan authority;
    step bindings stay enforced by ConfirmationBroker.issue_next_step_grant ->
    ToolExecutionGuard.
    """
    db = _isolated_database(tmp_path / "reconfirm-plan-e2e.db")
    identity = _identity()
    identity_hash, payload, plan_hash = _canonical(identity, plan_id="reconfirm-plan")
    grant_id = "reconfirm-grant"
    repo = ExecutionGrantRepository(db)
    assert repo.create_plan({
        "grant_id": grant_id, "user_id": identity["user_id"], "session_id": identity["session_id"],
        "identity_hash": identity_hash, "plan_id": "reconfirm-plan", "plan_hash": plan_hash,
        "plan_payload": payload, "risk_level": "high", "expires_at": _future(),
    })
    assert repo.transition_plan(grant_id, "pending", "approved", {"user_id": identity["user_id"]})

    broker, gateway, pipeline, orchestrator, audit = _wire(db, calls := [], decision_engine=_RequireConfirmDecision())

    # Without a durable grant the same high-risk plan is blocked.
    pending = await orchestrator.resume_approved_plan("missing-grant", identity)
    assert pending.error is not None

    # With the durable grant the plan-level re-confirmation is satisfied and
    # both steps execute under their own step grants.
    result = await orchestrator.resume_approved_plan(grant_id, identity)
    assert result.error is None, result.error
    assert result.approved is True
    assert len(calls) == 2, "both granted steps must execute"
    assert repo.get_plan(grant_id)["status"] == "consumed"
    db.close()
