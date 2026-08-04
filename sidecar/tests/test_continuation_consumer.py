import asyncio
import os
from datetime import datetime, timedelta, timezone

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


class _FakeOrchestrator:
    def __init__(self, plan_summary="read Downloads/report.pdf"):
        self._plan_summary = plan_summary

    async def process(self, utterance, *, identity=None, session_id=None, dry_run=False, timeout=None):
        from types import SimpleNamespace

        class _Plan:
            summary = self._plan_summary

        return SimpleNamespace(plan=_Plan(), error=None, tool_result=None)


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
    # Stored version is durable.
    loaded = svc.get(ctx.continuation_id)
    assert loaded is not None
    assert loaded.state == ContinuationState.AWAITING_CONFIRMATION
    assert loaded.version >= 2


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

    monkeypatch.setattr("modules.sentinel_bridge_helpers.get_orchestrator", lambda: _BrokenOrchestrator())
    executor = ContinuationExecutor(continuation_service=svc)
    result = await executor.start(
        continuation_id=ctx.continuation_id,
        user_id="u1",
        session_id="s1",
    )
    assert result is not None
    assert result["state"] == ContinuationState.FAILED
