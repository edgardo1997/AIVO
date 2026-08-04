import os
import time
from datetime import datetime, timedelta, timezone

import pytest

from repositories.clarification_store import ClarificationRecord, ClarificationStore
from services.clarification_continuation import (
    ClarifiedRequestContext,
    ContinuationService,
    ContinuationState,
    MaterialChangeFlags,
)
from services.clarification_service import ClarificationService


def _record(state="pending", free_text_allowed=True):
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
        candidate_ids=[],
        candidate_metadata=[],
        free_text_allowed=free_text_allowed,
        allow_none=True,
        state=state,
        created_at=datetime.now(timezone.utc).isoformat(),
        expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        version=1,
    )


@pytest.mark.alpha_constitutional_gate
def test_resolve_creates_clarified_request_context(tmp_path):
    store = ClarificationStore(path=tmp_path / "c.json")
    cont_path = tmp_path / "continuations.json"
    continuation_store = __import__("repositories.continuation_store", fromlist=["ContinuationStore"]).ContinuationStore(path=cont_path)
    svc = ClarificationService(store=store, continuation_service=ContinuationService(store=continuation_store))
    rec = _record()
    store.put(rec)
    resolved = svc.resolve(
        rec.clarification_id,
        session_id=rec.session_id,
        user_id=rec.user_id,
        correlation_id=rec.correlation_id,
        version=1,
        free_text_response="report.pdf",
    )
    assert resolved is not None
    assert resolved.continuation_id
    assert resolved.resolved_utterance == "report.pdf"
    cont = continuation_store.get(resolved.continuation_id)
    assert cont is not None
    assert cont["state"] == ContinuationState.REPLANNING
    assert cont["resolved_utterance"] == "report.pdf"
    assert cont["clarification_id"] == resolved.clarification_id


@pytest.mark.alpha_constitutional_gate
def test_continuation_has_material_change_flags(tmp_path):
    store = ClarificationStore(path=tmp_path / "c.json")
    cont_path = tmp_path / "continuations.json"
    continuation_store = __import__("repositories.continuation_store", fromlist=["ContinuationStore"]).ContinuationStore(path=cont_path)
    svc = ClarificationService(store=store, continuation_service=ContinuationService(store=continuation_store))
    rec = _record()
    store.put(rec)
    resolved = svc.resolve(
        rec.clarification_id,
        session_id=rec.session_id,
        user_id=rec.user_id,
        correlation_id=rec.correlation_id,
        version=1,
        free_text_response="report.pdf",
    )
    cont = continuation_store.get(resolved.continuation_id)
    flags = cont["material_change_flags"]
    assert flags["intent_changed"]
    assert flags["arguments_changed"]
    assert not flags["tool_changed"]


@pytest.mark.alpha_constitutional_gate
def test_resolve_is_idempotent_no_duplicate_execution(tmp_path):
    store = ClarificationStore(path=tmp_path / "c.json")
    cont_path = tmp_path / "continuations.json"
    continuation_store = __import__("repositories.continuation_store", fromlist=["ContinuationStore"]).ContinuationStore(path=cont_path)
    svc = ClarificationService(store=store, continuation_service=ContinuationService(store=continuation_store))
    rec = _record()
    store.put(rec)
    first = svc.resolve(
        rec.clarification_id,
        session_id=rec.session_id,
        user_id=rec.user_id,
        correlation_id=rec.correlation_id,
        version=1,
        free_text_response="report.pdf",
    )
    second = svc.resolve(
        rec.clarification_id,
        session_id=rec.session_id,
        user_id=rec.user_id,
        correlation_id=rec.correlation_id,
        version=1,
        free_text_response="report.pdf",
    )
    # Replaying the same consumed record returns None.
    assert first is not None
    assert second is None
    assert len(continuation_store.get_pending(rec.session_id, rec.user_id)) == 1


@pytest.mark.alpha_constitutional_gate
def test_cancellation_creates_no_continuation(tmp_path):
    store = ClarificationStore(path=tmp_path / "c.json")
    cont_path = tmp_path / "continuations.json"
    continuation_store = __import__("repositories.continuation_store", fromlist=["ContinuationStore"]).ContinuationStore(path=cont_path)
    svc = ClarificationService(store=store, continuation_service=ContinuationService(store=continuation_store))
    rec = _record()
    store.put(rec)
    cancelled = svc.cancel(
        rec.clarification_id,
        session_id=rec.session_id,
        user_id=rec.user_id,
        correlation_id=rec.correlation_id,
        version=1,
    )
    assert cancelled is not None
    assert cancelled.state == "cancelled"
    assert not continuation_store.get_pending(rec.session_id, rec.user_id)
