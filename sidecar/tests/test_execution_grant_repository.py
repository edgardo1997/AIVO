"""Repository-only evidence for the inactive durable execution-grant schema."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import sqlite3
from unittest.mock import MagicMock

import pytest

from repositories.database import DatabaseManager, LATEST_SCHEMA_VERSION
from repositories.execution_grant_repository import ExecutionGrantRepository
from repositories.audit_repository import AuditRepository
from services.audit_service import AuditService
from sentinel.core.confirmation import ConfirmationBroker
from sentinel.core.execution_pipeline import ExecutionPipeline
from sentinel.core.orchestrator import Orchestrator
from sentinel.core.policy import PolicyEffect
from sentinel.core.policy_engine import PolicyEngine
from sentinel.core.tool import Tool, ToolResult, ToolSpec
from sentinel.core.tool_gateway import ToolGateway
from sentinel.security.tool_guard import ToolExecutionGuard


def _future(minutes=10):
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z")


def _plan(grant_id="plan-1", **overrides):
    value = {
        "grant_id": grant_id, "user_id": "user-1", "session_id": "session-1",
        "identity_hash": "identity-1", "plan_id": "plan-id-1", "plan_hash": "plan-hash-1",
        "plan_payload": "{\"steps\":[]}", "risk_level": "high", "expires_at": _future(),
    }
    value.update(overrides)
    return value


def _step(plan_grant_id="plan-1", step_grant_id="step-1", **overrides):
    value = {
        "step_grant_id": step_grant_id, "plan_grant_id": plan_grant_id,
        "plan_id": "plan-id-1", "plan_hash": "plan-hash-1", "step_id": "step-id-1",
        "step_index": 0, "tool_id": "tool-1", "params_hash": "params-1",
        "identity_hash": "identity-1", "session_id": "session-1", "expires_at": _future(),
    }
    value.update(overrides)
    return value


def _binding(**overrides):
    value = {key: _step()[key] for key in (
        "plan_grant_id", "plan_id", "plan_hash", "step_id", "step_index", "tool_id",
        "params_hash", "identity_hash", "session_id",
    )}
    value.update(overrides)
    return value


@pytest.fixture
def grants_db():
    db = DatabaseManager()
    with db.transaction(immediate=True) as conn:
        conn.execute("DELETE FROM execution_grant_audit")
        conn.execute("DELETE FROM step_execution_grants")
        conn.execute("DELETE FROM plan_approval_grants")
    return db, ExecutionGrantRepository(db)


def _approve(repo, grant_id="plan-1"):
    assert repo.transition_plan(grant_id, "pending", "approved", {"user_id": "user-1"})


def _isolated_database(path):
    """Bypass the singleton only for a disposable migration fixture."""
    db = object.__new__(DatabaseManager)
    db._init(str(path))
    return db


class _DurableE2ETool(Tool):
    def __init__(self, tool_id, calls, fail=False):
        self._tool_id, self._calls, self._fail = tool_id, calls, fail

    def spec(self):
        return ToolSpec(self._tool_id, self._tool_id, "durable e2e", "1", {}, ["test.execute"])

    async def execute(self, params, context):
        self._calls.append((self._tool_id, params, context.get("execution_grant")))
        return ToolResult.fail("intentional failure", self._tool_id) if self._fail else ToolResult.ok({"ok": True}, self._tool_id)


@pytest.mark.unit
def test_v7_to_v8_migration_is_idempotent_and_preserves_legacy(tmp_path):
    path = tmp_path / "v7.db"
    initial = _isolated_database(path)
    conn = initial._get_conn()
    conn.execute(
        "INSERT INTO pending_actions (action_id, tool_id, params, reason, created_at, ttl_seconds, confirmed) "
        "VALUES ('legacy-1','old-tool','{}','legacy','2026-01-01T00:00:00Z',60,1)"
    )
    conn.execute("DROP TABLE execution_grant_audit")
    conn.execute("DROP TABLE step_execution_grants")
    conn.execute("DROP TABLE plan_approval_grants")
    conn.execute("DELETE FROM schema_migrations WHERE version=8")
    conn.execute("PRAGMA user_version=7")
    conn.commit()
    initial.close()

    migrated = _isolated_database(path)
    tables = {row["name"] for row in migrated._get_conn().execute("SELECT name FROM sqlite_master WHERE type='table'")}
    indexes = {row["name"] for row in migrated._get_conn().execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert {"plan_approval_grants", "step_execution_grants", "execution_grant_audit"} <= tables
    assert {"idx_plan_grants_status", "idx_step_grants_status", "idx_grant_audit_grant"} <= indexes
    assert migrated.fetchone("SELECT confirmed FROM pending_actions WHERE action_id='legacy-1'") == {"confirmed": 0}
    assert migrated.fetchone("SELECT * FROM plan_approval_grants") is None
    assert migrated.schema_version == 8
    migrated._run_migrations()
    assert migrated.schema_version == 8
    migrated.close()


@pytest.mark.unit
def test_fresh_database_reaches_latest_schema(tmp_path):
    db = _isolated_database(tmp_path / "fresh.db")
    assert db.schema_version == LATEST_SCHEMA_VERSION
    assert db.fetchone("SELECT name FROM sqlite_master WHERE type='table' AND name='plan_approval_grants'")
    db.close()


@pytest.mark.unit
def test_plan_state_machine_and_expiry(grants_db):
    _, repo = grants_db
    assert repo.create_plan(_plan())
    assert repo.transition_plan("plan-1", "pending", "approved", {})
    assert repo.transition_plan("plan-1", "approved", "in_progress", {})
    assert repo.transition_plan("plan-1", "in_progress", "consumed", {})
    assert not repo.transition_plan("plan-1", "consumed", "approved", {})
    assert repo.get_plan("plan-1")["status"] == "consumed"
    assert repo.create_plan(_plan("expired", expires_at=_future(-1)))
    assert not repo.transition_plan("expired", "pending", "approved", {})
    assert repo.get_plan("expired")["status"] == "expired"


@pytest.mark.unit
def test_rejection_and_invalid_transitions_leave_plan_unchanged(grants_db):
    _, repo = grants_db
    repo.create_plan(_plan())
    assert not repo.transition_plan("plan-1", "pending", "consumed", {})
    assert repo.get_plan("plan-1")["status"] == "pending"
    assert repo.transition_plan("plan-1", "pending", "rejected", {"reason": "user_declined"})
    assert repo.get_plan("plan-1")["status"] == "rejected"


@pytest.mark.unit
@pytest.mark.parametrize("state", ["pending", "rejected", "expired", "cancelled", "failed", "consumed"])
def test_step_creation_requires_approved_or_in_progress_plan(grants_db, state):
    _, repo = grants_db
    repo.create_plan(_plan())
    if state == "approved":
        _approve(repo)
    elif state != "pending":
        # The repository intentionally rejects unsupported direct transitions.
        repo.transition_plan("plan-1", "pending", "rejected", {})
    assert not repo.create_step(_step())


@pytest.mark.unit
def test_step_consumption_binds_every_effect_input_and_audits_rejection(grants_db):
    db, repo = grants_db
    repo.create_plan(_plan())
    _approve(repo)
    assert repo.create_step(_step())
    for key, value in {
        "plan_grant_id": "other", "plan_id": "other", "plan_hash": "other", "step_id": "other",
        "step_index": 1, "tool_id": "other", "params_hash": "other", "identity_hash": "other",
        "session_id": "other",
    }.items():
        assert not repo.consume_step("step-1", _binding(**{key: value}))
    assert repo.consume_step("step-1", _binding())
    assert not repo.consume_step("step-1", _binding())
    assert db.fetchone("SELECT COUNT(*) AS n FROM execution_grant_audit WHERE event_type='replay_or_mismatch'")["n"] == 10


@pytest.mark.unit
def test_step_cannot_be_created_from_mismatched_parent_bindings(grants_db):
    _, repo = grants_db
    repo.create_plan(_plan())
    _approve(repo)
    assert not repo.create_step(_step(plan_hash="other"))


@pytest.mark.unit
def test_step_can_be_derived_from_in_progress_plan(grants_db):
    _, repo = grants_db
    repo.create_plan(_plan())
    _approve(repo)
    assert repo.transition_plan("plan-1", "approved", "in_progress", {})
    assert repo.create_step(_step())


@pytest.mark.unit
def test_concurrent_approvals_have_one_winner(grants_db):
    _, repo = grants_db
    repo.create_plan(_plan())
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: repo.transition_plan("plan-1", "pending", "approved", {}), range(2)))
    assert results.count(True) == 1
    assert results.count(False) == 1


@pytest.mark.unit
def test_concurrent_step_consumers_have_one_winner(grants_db):
    _, repo = grants_db
    repo.create_plan(_plan())
    _approve(repo)
    assert repo.create_step(_step())
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: repo.consume_step("step-1", _binding()), range(2)))
    assert results.count(True) == 1
    assert results.count(False) == 1
    assert repo.get_step("step-1")["status"] == "consumed"


@pytest.mark.unit
def test_grants_and_audit_survive_reopen(grants_db):
    db, repo = grants_db
    repo.create_plan(_plan())
    _approve(repo)
    repo.create_step(_step())
    assert repo.consume_step("step-1", _binding())
    db.close_connections()
    assert repo.get_plan("plan-1")["status"] == "approved"
    assert repo.get_step("step-1")["status"] == "consumed"
    assert db.fetchone("SELECT COUNT(*) AS n FROM execution_grant_audit")["n"] >= 4


@pytest.mark.unit
def test_expiration_and_audit_survive_reopen(grants_db):
    db, repo = grants_db
    repo.create_plan(_plan(expires_at=_future(-1)))
    assert not repo.transition_plan("plan-1", "pending", "approved", {})
    db.close_connections()
    assert repo.get_plan("plan-1")["status"] == "expired"
    assert db.fetchone("SELECT event_type FROM execution_grant_audit WHERE grant_id='plan-1' ORDER BY event_id DESC")["event_type"] == "expired"


def test_approved_plan_recovers_after_restart_and_rejects_mutation(grants_db):
    db, repo = grants_db
    payload, plan_hash = ConfirmationBroker.canonical_plan({"plan_id": "plan-id-1", "steps": [{"id": "step-id-1", "tool_id": "tool-1", "params": {"a": 1}}]})
    repo.create_plan(_plan(plan_payload=payload, plan_hash=plan_hash))
    _approve(repo)
    broker = ConfirmationBroker(memory=None)
    broker._grants = repo
    assert broker.recover_approved_plan("plan-1")["steps"][0]["tool_id"] == "tool-1"
    db._get_conn().execute("UPDATE plan_approval_grants SET plan_payload='{}' WHERE grant_id='plan-1'")
    with pytest.raises(PermissionError, match="hash mismatch"):
        broker.recover_approved_plan("plan-1")


def test_broker_derives_typed_step_context(grants_db):
    _, repo = grants_db
    repo.create_plan(_plan())
    _approve(repo)
    broker = ConfirmationBroker(memory=None)
    broker._grants = repo
    context = broker.issue_step_grant(_step())
    assert context.plan_grant_id == "plan-1"
    assert context.step_grant_id == "step-1"
    assert context.tool_id == "tool-1"


def test_broker_issues_steps_in_order_and_binds_distinct_grants(grants_db):
    _, repo = grants_db
    identity_hash = ConfirmationBroker._hash({"user_id": "user-1", "session_id": "session-1"})
    payload, plan_hash = ConfirmationBroker.canonical_plan({"plan_id": "plan-id-1", "steps": [{"id": "step-0"}, {"id": "step-1"}]})
    repo.create_plan(_plan(identity_hash=identity_hash, plan_payload=payload, plan_hash=plan_hash))
    _approve(repo)
    broker = ConfirmationBroker(memory=None)
    broker._grants = repo
    broker.resume_approved_plan("plan-1", user_id="user-1", session_id="session-1", identity_hash=identity_hash)
    first = broker.issue_next_step_grant(
        plan_grant_id="plan-1", user_id="user-1", session_id="session-1", identity_hash=identity_hash,
        step_id="step-0", step_index=0, tool_id="tool-0", params={"n": 0}, expires_at=_future(),
    )
    with pytest.raises(PermissionError, match="step order"):
        broker.issue_next_step_grant(
            plan_grant_id="plan-1", user_id="user-1", session_id="session-1", identity_hash=identity_hash,
            step_id="step-1", step_index=1, tool_id="tool-1", params={"n": 1}, expires_at=_future(),
        )
    assert broker.consume_step_grant(first.step_grant_id, {
        "plan_grant_id": first.plan_grant_id, "plan_id": first.plan_id, "plan_hash": first.plan_hash,
        "step_id": first.step_id, "step_index": first.step_index, "tool_id": first.tool_id,
        "params_hash": first.params_hash, "identity_hash": first.identity_hash, "session_id": first.session_id,
    })
    second = broker.issue_next_step_grant(
        plan_grant_id="plan-1", user_id="user-1", session_id="session-1", identity_hash=identity_hash,
        step_id="step-1", step_index=1, tool_id="tool-1", params={"n": 1}, expires_at=_future(),
    )
    assert first.step_grant_id != second.step_grant_id
    assert broker.complete_plan("plan-1", user_id="user-1", session_id="session-1", identity_hash=identity_hash) is False


@pytest.mark.unit
def test_locked_sqlite_and_transaction_failure_fail_closed_without_false_consumption(grants_db, monkeypatch):
    db, repo = grants_db
    repo.create_plan(_plan())
    _approve(repo)
    repo.create_step(_step())
    lock = sqlite3.connect(db.db_path, timeout=0.01, isolation_level=None)
    lock.execute("BEGIN IMMEDIATE")
    db._get_conn().execute("PRAGMA busy_timeout=1")
    with pytest.raises(sqlite3.OperationalError):
        repo.consume_step("step-1", _binding())
    lock.rollback()
    lock.close()
    assert repo.get_step("step-1")["status"] == "approved"
    before = db.fetchone("SELECT COUNT(*) AS n FROM execution_grant_audit")["n"]
    monkeypatch.setattr(repo, "_audit", lambda *args: (_ for _ in ()).throw(RuntimeError("audit down")))
    with pytest.raises(RuntimeError, match="audit down"):
        repo.consume_step("step-1", _binding())
    assert repo.get_step("step-1")["status"] == "approved"
    assert db.fetchone("SELECT COUNT(*) AS n FROM execution_grant_audit")["n"] == before


@pytest.mark.integration
@pytest.mark.asyncio
async def test_durable_multistep_execution_grants_reach_real_executor_and_survive_restart(tmp_path):
    """Production-path E2E: SQLite -> broker -> typed context -> guard -> gateway -> tool."""
    db = _isolated_database(tmp_path / "durable-e2e.db")
    repo = ExecutionGrantRepository(db)
    identity_hash = ConfirmationBroker._hash({"user_id": "user-e2e", "session_id": "session-e2e"})
    payload, plan_hash = ConfirmationBroker.canonical_plan({
        "plan_id": "plan-e2e",
        "steps": [
            {"id": "one", "tool_id": "e2e.one", "params": {"n": 1}},
            {"id": "two", "tool_id": "e2e.two", "params": {"n": 2}},
        ],
    })
    assert repo.create_plan(_plan("plan-e2e-grant", user_id="user-e2e", session_id="session-e2e", identity_hash=identity_hash, plan_id="plan-e2e", plan_hash=plan_hash, plan_payload=payload))
    assert repo.transition_plan("plan-e2e-grant", "pending", "approved", {"user_id": "user-e2e"})
    db.close_connections()  # restart before execution
    broker = ConfirmationBroker(memory=None)
    broker._grants = ExecutionGrantRepository(db)
    broker.resume_approved_plan("plan-e2e-grant", user_id="user-e2e", session_id="session-e2e", identity_hash=identity_hash)
    calls = []
    gateway = ToolGateway(policy_engine=PolicyEngine(default_effect=PolicyEffect.ALLOW))
    gateway.set_confirmation_broker(broker)
    gateway.register(_DurableE2ETool("e2e.one", calls))
    gateway.register(_DurableE2ETool("e2e.two", calls))
    gateway._audit_service = AuditService(AuditRepository(db))
    guard = ToolExecutionGuard(
        tool_gateway=gateway,
        policy_engine=gateway._policy_engine,
        audit_service=gateway._audit_service,
    )
    pipeline = ExecutionPipeline(gateway, guard)
    pipeline.set_confirmation_broker(broker)
    context = {"identity": {"user_id": "user-e2e", "session_id": "session-e2e", "is_authenticated": True, "permissions": ["test.execute"]}}
    first = broker.issue_next_step_grant(plan_grant_id="plan-e2e-grant", user_id="user-e2e", session_id="session-e2e", identity_hash=identity_hash, step_id="one", step_index=0, tool_id="e2e.one", params={"n": 1}, expires_at=_future())
    first_result = await pipeline.execute("e2e.one", {"n": 1}, context, source="approved_plan", execution_grant=first)
    assert first_result.success and calls[-1][2].step_grant_id == first.step_grant_id
    db.close_connections()  # restart between steps
    broker = ConfirmationBroker(memory=None)
    broker._grants = ExecutionGrantRepository(db)
    pipeline.set_confirmation_broker(broker)
    second = broker.issue_next_step_grant(plan_grant_id="plan-e2e-grant", user_id="user-e2e", session_id="session-e2e", identity_hash=identity_hash, step_id="two", step_index=1, tool_id="e2e.two", params={"n": 2}, expires_at=_future())
    assert second.step_grant_id != first.step_grant_id
    replay = await pipeline.execute("e2e.one", {"n": 1}, context, source="approved_plan", execution_grant=first)
    assert not replay.success and len(calls) == 1
    second_result = await pipeline.execute("e2e.two", {"n": 2}, context, source="approved_plan", execution_grant=second)
    assert second_result.success and len(calls) == 2
    assert broker.complete_plan("plan-e2e-grant", user_id="user-e2e", session_id="session-e2e", identity_hash=identity_hash)
    assert repo.get_plan("plan-e2e-grant")["status"] == "consumed"
    audit = db.fetchone("SELECT COUNT(*) AS n FROM execution_grant_audit")
    assert audit["n"] >= 7
    db.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_resume_approved_plan_reaches_real_guarded_executor(tmp_path):
    """The productive resume entrypoint cannot bypass durable grants."""
    db = _isolated_database(tmp_path / "resume-e2e.db")
    repo = ExecutionGrantRepository(db)
    identity = {"user_id": "resume-user", "session_id": "resume-session", "is_authenticated": True, "permissions": ["test.execute"]}
    identity_hash = ConfirmationBroker._hash({"user_id": identity["user_id"], "session_id": identity["session_id"]})
    payload, plan_hash = ConfirmationBroker.canonical_plan({
        "plan_id": "resume-plan", "intent": {"action": "execute", "target": "e2e.resume", "parameters": {}, "confidence": 1.0, "raw_input": "resume"},
        "steps": [{"id": "only", "tool_id": "e2e.resume", "params": {"ok": True}}],
    })
    assert repo.create_plan(_plan("resume-grant", user_id=identity["user_id"], session_id=identity["session_id"], identity_hash=identity_hash, plan_id="resume-plan", plan_hash=plan_hash, plan_payload=payload))
    assert repo.transition_plan("resume-grant", "pending", "approved", {})
    db.close_connections()
    broker = ConfirmationBroker(memory=None)
    broker._grants = ExecutionGrantRepository(db)
    calls = []
    gateway = ToolGateway(policy_engine=PolicyEngine(default_effect=PolicyEffect.ALLOW))
    gateway.set_confirmation_broker(broker)
    gateway.register(_DurableE2ETool("e2e.resume", calls))
    audit = AuditService(AuditRepository(db))
    gateway._audit_service = audit
    guard = ToolExecutionGuard(tool_gateway=gateway, policy_engine=gateway._policy_engine, audit_service=audit)
    pipeline = ExecutionPipeline(gateway, guard)
    pipeline.set_confirmation_broker(broker)
    intent_engine = MagicMock()
    intent_engine.list_supported_targets.return_value = []
    orchestrator = Orchestrator(intent_engine=intent_engine, tool_gateway=gateway, execution_pipeline=pipeline, audit_service=audit)
    result = await orchestrator.resume_approved_plan("resume-grant", identity)
    assert result.error is None
    assert [call[0] for call in calls] == ["e2e.resume"]
    assert calls[0][2].plan_grant_id == "resume-grant"
    assert repo.get_step(calls[0][2].step_grant_id)["status"] == "consumed"
    assert repo.get_plan("resume-grant")["status"] == "consumed"
    db.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_failed_resumed_plan_is_durable_and_cannot_issue_following_step(tmp_path):
    db = _isolated_database(tmp_path / "resume-failed.db")
    repo = ExecutionGrantRepository(db)
    identity = {"user_id": "fail-user", "session_id": "fail-session", "is_authenticated": True, "permissions": ["test.execute"]}
    identity_hash = ConfirmationBroker._hash({"user_id": identity["user_id"], "session_id": identity["session_id"]})
    payload, plan_hash = ConfirmationBroker.canonical_plan({"plan_id": "fail-plan", "intent": {"action": "execute", "target": "e2e.fail", "parameters": {}, "confidence": 1.0, "raw_input": "fail"}, "steps": [{"id": "bad", "tool_id": "e2e.fail", "params": {}}, {"id": "never", "tool_id": "e2e.never", "params": {}}]})
    assert repo.create_plan(_plan("fail-grant", user_id=identity["user_id"], session_id=identity["session_id"], identity_hash=identity_hash, plan_id="fail-plan", plan_hash=plan_hash, plan_payload=payload))
    assert repo.transition_plan("fail-grant", "pending", "approved", {})
    broker = ConfirmationBroker(memory=None)
    broker._grants = repo
    calls = []
    gateway = ToolGateway(policy_engine=PolicyEngine(default_effect=PolicyEffect.ALLOW))
    gateway.set_confirmation_broker(broker)
    gateway.register(_DurableE2ETool("e2e.fail", calls, fail=True))
    gateway.register(_DurableE2ETool("e2e.never", calls))
    audit = AuditService(AuditRepository(db))
    gateway._audit_service = audit
    guard = ToolExecutionGuard(tool_gateway=gateway, policy_engine=gateway._policy_engine, audit_service=audit)
    pipeline = ExecutionPipeline(gateway, guard)
    pipeline.set_confirmation_broker(broker)
    engine = MagicMock()
    engine.list_supported_targets.return_value = []
    result = await Orchestrator(intent_engine=engine, tool_gateway=gateway, execution_pipeline=pipeline, audit_service=audit).resume_approved_plan("fail-grant", identity)
    assert result.error == "intentional failure"
    assert repo.get_plan("fail-grant")["status"] == "failed"
    assert len(calls) == 1
    with pytest.raises(PermissionError):
        broker.issue_next_step_grant(plan_grant_id="fail-grant", user_id=identity["user_id"], session_id=identity["session_id"], identity_hash=identity_hash, step_id="never", step_index=1, tool_id="e2e.never", params={}, expires_at=_future())
    db.close()
