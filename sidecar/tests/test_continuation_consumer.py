import asyncio
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from repositories.clarification_store import ClarificationRecord
from repositories.continuation_store import ContinuationStore
from services.clarification_continuation import (
    ClarifiedRequestContext,
    ContinuationService,
    ContinuationState,
    MaterialChangeFlags,
)
from services.continuation_executor import ContinuationExecutor


def _clarification_record():
    return ClarificationRecord(
        clarification_id=f"c-{os.urandom(4).hex()}",
        correlation_id="corr-1",
        session_id="s1",
        user_id="u1",
        original_request_id="req-1",
        ambiguity_decision_id="d1",
        input_understanding_id="i1",
        question="Which file?",
        response_language="en",
        ambiguity_type="entity",
        candidate_ids=["a"],
        candidate_metadata=[{"id": "a", "label": "report.pdf"}],
        free_text_allowed=True,
        allow_none=True,
        state="pending",
        created_at=datetime.now(timezone.utc).isoformat(),
        expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        version=1,
        resolved_action="read",
        resolved_target="Downloads/report.pdf",
    )


class _FakeBroker:
    @staticmethod
    def _hash(obj):
        return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]

    @staticmethod
    def canonical_plan(plan_dict):
        payload = json.dumps(plan_dict, sort_keys=True, default=str)
        return payload, hashlib.sha256(payload.encode()).hexdigest()

    def request_continuation_grant(self, **kwargs):
        return "plan-grant-1"

    def approve_continuation_grant(self, grant_id, *, user_id):
        return True

    class _Grants:
        @staticmethod
        def transition_plan(*args, **kwargs):
            return True

    _grants = _Grants()


class _Plan:
    summary = "read Downloads/report.pdf"
    description = "read Downloads/report.pdf"
    risk_score = 0.1
    steps = [SimpleNamespace(id="s1", tool_id="filesystem.read", params={"path": "Downloads/report.pdf"}, description="read", is_reversible=True)]


class _FakeOrchestrator:
    def __init__(self, plan=None, error=None, approved=False):
        self._plan = plan or _Plan()
        self._error = error
        self._approved = approved
        self._tool_gateway = SimpleNamespace(_confirmation_broker=_FakeBroker())

    async def process(self, utterance, *, identity=None, session_id=None, dry_run=False, approved_plan_grant_id=None, timeout=None):
        # Mirror the real ExecutionResult contract: presentation defaults to None.
        result = SimpleNamespace(plan=self._plan, error=self._error, presentation=None)
        if not dry_run:
            result.tool_result = SimpleNamespace(success=self._approved)
            result.execution_id = "exec-1"
            result.approved = self._approved
        return result


class _ChangingOrchestrator:
    """Returns a different plan on the second dry-run call to exercise TOCTOU."""

    def __init__(self):
        self._calls = 0
        self._original = _Plan()
        self._changed = _Plan()
        self._changed.steps = [SimpleNamespace(id="s2", tool_id="filesystem.read", params={"path": "Downloads/other.pdf"}, description="read", is_reversible=True)]
        self._tool_gateway = SimpleNamespace(_confirmation_broker=_FakeBroker())

    async def process(self, utterance, *, identity=None, session_id=None, dry_run=False, approved_plan_grant_id=None, timeout=None):
        self._calls += 1
        plan = self._original if self._calls == 1 else self._changed
        result = SimpleNamespace(plan=plan, error=None)
        if not dry_run:
            result.tool_result = SimpleNamespace(success=True)
            result.execution_id = "exec-1"
            result.approved = True
        return result


def _create_continuation(tmp_path):
    store = ContinuationStore(path=tmp_path / "continuations.json")
    svc = ContinuationService(store=store)
    record = _clarification_record()
    ctx = svc.create_continuation(
        record=record,
        resolved_utterance="read Downloads/report.pdf",
        resolved_target="Downloads/report.pdf",
        material_change_flags=MaterialChangeFlags(target_changed=True),
        idempotency_key="idem-1",
    )
    return ctx, store, svc


@pytest.mark.alpha_constitutional_gate
def test_continuation_created_state_and_metadata(tmp_path):
    ctx, _, _ = _create_continuation(tmp_path)
    assert ctx.state == ContinuationState.CREATED
    assert ctx.continuation_id
    assert ctx.new_correlation_id
    assert ctx.parent_request_id == "req-1"
    assert ctx.material_change_flags.target_changed is True


@pytest.mark.asyncio
@pytest.mark.alpha_constitutional_gate
async def test_start_loads_context_and_transitions_to_awaiting_confirmation(tmp_path, monkeypatch):
    ctx, store, svc = _create_continuation(tmp_path)
    monkeypatch.setattr("modules.sentinel_bridge_helpers.get_orchestrator", lambda: _FakeOrchestrator())
    executor = ContinuationExecutor(continuation_service=svc)
    result = await executor.start(
        continuation_id=ctx.continuation_id,
        user_id="u1",
        session_id="s1",
        identity={"user_id": "u1"},
    )
    assert result is not None
    assert result["state"] == ContinuationState.AWAITING_CONFIRMATION
    assert result["requires_confirmation"] is True
    assert result["resolved_utterance"] == "read Downloads/report.pdf"
    assert result["confirmation_id"] == "plan-grant-1"
    # Stored version is durable.
    loaded = svc.get(ctx.continuation_id)
    assert loaded is not None
    assert loaded.state == ContinuationState.AWAITING_CONFIRMATION
    assert loaded.version >= 2
    assert loaded.confirmation_id == "plan-grant-1"


@pytest.mark.asyncio
@pytest.mark.alpha_constitutional_gate
async def test_cross_user_start_denied(tmp_path, monkeypatch):
    ctx, _, svc = _create_continuation(tmp_path)
    monkeypatch.setattr("modules.sentinel_bridge_helpers.get_orchestrator", lambda: _FakeOrchestrator())
    executor = ContinuationExecutor(continuation_service=svc)
    result = await executor.start(
        continuation_id=ctx.continuation_id,
        user_id="u2",
        session_id="s1",
    )
    assert result is None


@pytest.mark.asyncio
@pytest.mark.alpha_constitutional_gate
async def test_cross_session_start_denied(tmp_path, monkeypatch):
    ctx, _, svc = _create_continuation(tmp_path)
    monkeypatch.setattr("modules.sentinel_bridge_helpers.get_orchestrator", lambda: _FakeOrchestrator())
    executor = ContinuationExecutor(continuation_service=svc)
    result = await executor.start(
        continuation_id=ctx.continuation_id,
        user_id="u1",
        session_id="s2",
    )
    assert result is None


@pytest.mark.asyncio
@pytest.mark.alpha_constitutional_gate
async def test_duplicate_start_is_idempotent(tmp_path, monkeypatch):
    ctx, _, svc = _create_continuation(tmp_path)
    monkeypatch.setattr("modules.sentinel_bridge_helpers.get_orchestrator", lambda: _FakeOrchestrator())
    executor = ContinuationExecutor(continuation_service=svc)
    first = await executor.start(
        continuation_id=ctx.continuation_id,
        user_id="u1",
        session_id="s1",
    )
    second = await executor.start(
        continuation_id=ctx.continuation_id,
        user_id="u1",
        session_id="s1",
    )
    assert first is not None
    assert second is not None
    # Second call does not trigger a new pipeline run for an already terminal/awaiting state.
    assert second["state"] == ContinuationState.AWAITING_CONFIRMATION
    assert second["version"] == first["version"]


@pytest.mark.alpha_constitutional_gate
def test_continuation_state_transition_validation(tmp_path):
    ctx, _, _ = _create_continuation(tmp_path)
    assert ctx.transition(ContinuationState.REPLANNING) is True
    assert ctx.transition(ContinuationState.AWAITING_CONFIRMATION) is True
    # Cannot go back to created.
    assert ctx.transition(ContinuationState.CREATED) is False
    # Cannot jump to completed from awaiting_confirmation.
    assert ctx.transition(ContinuationState.VERIFIED_COMPLETED) is False


@pytest.mark.alpha_constitutional_gate
def test_continuation_cancelled_is_terminal(tmp_path):
    ctx, _, _ = _create_continuation(tmp_path)
    assert ctx.transition(ContinuationState.CANCELLED) is True
    assert ctx.transition(ContinuationState.REPLANNING) is False
    assert ctx.state == ContinuationState.CANCELLED


@pytest.mark.asyncio
@pytest.mark.alpha_constitutional_gate
async def test_continuation_executor_fails_to_terminal(tmp_path, monkeypatch):
    ctx, _, svc = _create_continuation(tmp_path)

    class _BrokenOrchestrator:
        async def process(self, *args, **kwargs):
            raise RuntimeError("model unavailable")

        _tool_gateway = SimpleNamespace(_confirmation_broker=None)

    monkeypatch.setattr("modules.sentinel_bridge_helpers.get_orchestrator", lambda: _BrokenOrchestrator())
    executor = ContinuationExecutor(continuation_service=svc)
    result = await executor.start(
        continuation_id=ctx.continuation_id,
        user_id="u1",
        session_id="s1",
    )
    assert result is not None
    assert result["state"] == ContinuationState.FAILED


@pytest.mark.asyncio
@pytest.mark.alpha_constitutional_gate
async def test_confirm_approved_executes_to_verified_completion(tmp_path, monkeypatch):
    ctx, _, svc = _create_continuation(tmp_path)
    monkeypatch.setattr("modules.sentinel_bridge_helpers.get_orchestrator", lambda: _FakeOrchestrator(approved=True))
    executor = ContinuationExecutor(continuation_service=svc)
    started = await executor.start(ctx.continuation_id, "u1", "s1")
    assert started["state"] == ContinuationState.AWAITING_CONFIRMATION
    confirmed = await executor.confirm(ctx.continuation_id, "u1", "s1", approved=True)
    assert confirmed is not None
    assert confirmed["state"] == ContinuationState.VERIFIED_COMPLETED
    assert confirmed["execution_id"] == "exec-1"


@pytest.mark.asyncio
@pytest.mark.alpha_constitutional_gate
async def test_confirm_denied_is_terminal(tmp_path, monkeypatch):
    ctx, _, svc = _create_continuation(tmp_path)
    monkeypatch.setattr("modules.sentinel_bridge_helpers.get_orchestrator", lambda: _FakeOrchestrator())
    executor = ContinuationExecutor(continuation_service=svc)
    await executor.start(ctx.continuation_id, "u1", "s1")
    denied = await executor.confirm(ctx.continuation_id, "u1", "s1", approved=False)
    assert denied is not None
    assert denied["state"] == ContinuationState.DENIED


@pytest.mark.asyncio
@pytest.mark.alpha_constitutional_gate
async def test_cancel_before_execution_is_terminal(tmp_path, monkeypatch):
    ctx, _, svc = _create_continuation(tmp_path)
    monkeypatch.setattr("modules.sentinel_bridge_helpers.get_orchestrator", lambda: _FakeOrchestrator())
    executor = ContinuationExecutor(continuation_service=svc)
    await executor.start(ctx.continuation_id, "u1", "s1")
    cancelled = await executor.cancel(ctx.continuation_id, "u1", "s1")
    assert cancelled is not None
    assert cancelled["state"] == ContinuationState.CANCELLED


@pytest.mark.asyncio
@pytest.mark.alpha_constitutional_gate
async def test_toctou_plan_change_requires_replanning(tmp_path, monkeypatch):
    ctx, _, svc = _create_continuation(tmp_path)
    changing = _ChangingOrchestrator()
    monkeypatch.setattr("modules.sentinel_bridge_helpers.get_orchestrator", lambda: changing)
    executor = ContinuationExecutor(continuation_service=svc)
    await executor.start(ctx.continuation_id, "u1", "s1")
    # The confirm dry-run sees a different plan.
    result = await executor.confirm(ctx.continuation_id, "u1", "s1", approved=True)
    assert result is not None
    assert result["state"] == ContinuationState.REPLANNING
