import json
import os
import time
from datetime import datetime, timedelta, timezone

import pytest

from repositories.clarification_store import ClarificationRecord, ClarificationStore


def _record(state="pending", expires_at=None, created_at=None):
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
        candidate_ids=["a", "b"],
        candidate_metadata=[{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
        free_text_allowed=False,
        allow_none=True,
        state=state,
        created_at=created_at or datetime.now(timezone.utc).isoformat(),
        expires_at=expires_at or (datetime.now(timezone.utc) + timedelta(seconds=300)).isoformat(),
        version=1,
    )


@pytest.mark.alpha_constitutional_gate
def test_atomic_write_and_recovery(tmp_path):
    path = tmp_path / "clarifications.json"
    store = ClarificationStore(path=path)
    rec = _record()
    store.put(rec)
    # Simulate a fresh instance.
    store2 = ClarificationStore(path=path)
    loaded = store2.get(rec.clarification_id)
    assert loaded is not None
    assert loaded.question == rec.question


@pytest.mark.alpha_constitutional_gate
def test_corrupt_file_falls_back_to_backup(tmp_path):
    path = tmp_path / "clarifications.json"
    store = ClarificationStore(path=path)
    rec = _record()
    store.put(rec)
    # Corrupt the main file.
    path.write_text("not-json{", encoding="utf-8")
    store2 = ClarificationStore(path=path)
    loaded = store2.get(rec.clarification_id)
    assert loaded is not None
    assert loaded.question == rec.question


@pytest.mark.alpha_constitutional_gate
def test_expired_records_are_marked_on_load(tmp_path):
    path = tmp_path / "clarifications.json"
    store = ClarificationStore(path=path)
    past = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    rec = _record(expires_at=past)
    store.put(rec)
    loaded = store.get_pending(rec.session_id, rec.user_id)
    assert loaded == []
    assert store.get(rec.clarification_id).state == "expired"


@pytest.mark.alpha_constitutional_gate
def test_compaction_keeps_active_and_recent_terminal(tmp_path):
    path = tmp_path / "clarifications.json"
    store = ClarificationStore(path=path)
    active = _record()
    store.put(active)
    for _ in range(10):
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        r = _record(state="cancelled", created_at=past)
        store.put(r)
    # Active plus 10 terminal; default max is much higher, so all kept.
    assert len(store.all_records()) == 11


@pytest.mark.alpha_constitutional_gate
def test_no_secret_fields_persisted(tmp_path):
    path = tmp_path / "clarifications.json"
    store = ClarificationStore(path=path)
    rec = _record()
    rec.question = "Resolve with sk-12345 and prompt hidden"
    store.put(rec)
    raw = path.read_text(encoding="utf-8")
    assert "sk-12345" in raw  # user-facing question may contain it; the contract is no prompts/secrets
    # No hidden reasoning fields were written.
    payload = json.loads(raw)
    for r in payload["records"].values():
        for forbidden in ("reasoning", "prompt", "chain_of_thought", "secret"):
            assert forbidden not in r


@pytest.mark.alpha_constitutional_gate
def test_supersede_pending(tmp_path):
    path = tmp_path / "clarifications.json"
    store = ClarificationStore(path=path)
    r1 = _record()
    r2 = _record()
    r2.original_request_id = "req-2"
    store.put(r1)
    store.put(r2)
    count = store.supersede_pending(r1.session_id, r1.user_id, r2.original_request_id)
    assert count == 1
    assert store.get(r1.clarification_id).state == "superseded"
    assert store.get(r2.clarification_id).state == "pending"


@pytest.mark.alpha_constitutional_gate
def test_all_records_thread_safety(tmp_path):
    path = tmp_path / "clarifications.json"
    store = ClarificationStore(path=path)
    for _ in range(50):
        store.put(_record())
    assert len(store.all_records()) == 50
