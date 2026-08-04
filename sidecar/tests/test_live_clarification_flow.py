import pytest
from services import input_understanding_service as iu
from services.clarification_service import ClarificationService
from repositories.clarification_store import ClarificationStore


def _svc(tmp_path):
    store = ClarificationStore(path=tmp_path / "clarifications.json")
    return ClarificationService(store)


def _understanding_and_decision(text="borra ese archivo"):
    understanding = iu.resolve_input(text)
    understanding.candidate_targets = ["Downloads/report.pdf", "Desktop/report.pdf", "Documents/report.pdf"]
    understanding.ambiguity_type = "entity"
    understanding.risk_if_wrong = "medium"
    decision = iu.make_decision(understanding)
    if not decision.ask_clarification:
        decision.ask_clarification = True
        understanding.requires_clarification = True
    return understanding, decision


@pytest.mark.alpha_constitutional_gate
def test_create_emits_stable_candidate_ids(tmp_path):
    svc = _svc(tmp_path)
    understanding, decision = _understanding_and_decision()
    record = svc.create(understanding, decision, "s1", "u1", "req-1", "en", "corr-1")
    assert record.state == "pending"
    assert record.candidate_ids
    assert len(record.candidate_ids) == len(record.candidate_metadata)
    assert record.candidate_metadata[0]["id"] == record.candidate_ids[0]


@pytest.mark.alpha_constitutional_gate
def test_resolve_option_marks_consumed_and_builds_utterance(tmp_path):
    svc = _svc(tmp_path)
    understanding, decision = _understanding_and_decision()
    record = svc.create(understanding, decision, "s1", "u1", "req-1", "en", "corr-1")
    cid = record.candidate_ids[0]
    resolved = svc.resolve(
        record.clarification_id,
        session_id="s1",
        user_id="u1",
        correlation_id=record.correlation_id,
        version=record.version,
        selected_candidate_id=cid,
    )
    assert resolved is not None
    assert resolved.state == "consumed"
    assert resolved.selected_candidate_id == cid
    assert resolved.resolved_target


@pytest.mark.alpha_constitutional_gate
def test_resolve_wrong_session_fails(tmp_path):
    svc = _svc(tmp_path)
    understanding, decision = _understanding_and_decision()
    record = svc.create(understanding, decision, "s1", "u1", "req-1", "en", "corr-1")
    assert svc.resolve(
        record.clarification_id,
        session_id="s2",
        user_id="u1",
        correlation_id=record.correlation_id,
        version=record.version,
        selected_candidate_id=record.candidate_ids[0],
    ) is None


@pytest.mark.alpha_constitutional_gate
def test_resolve_wrong_user_fails(tmp_path):
    svc = _svc(tmp_path)
    understanding, decision = _understanding_and_decision()
    record = svc.create(understanding, decision, "s1", "u1", "req-1", "en", "corr-1")
    assert svc.resolve(
        record.clarification_id,
        session_id="s1",
        user_id="u2",
        correlation_id=record.correlation_id,
        version=record.version,
        selected_candidate_id=record.candidate_ids[0],
    ) is None


@pytest.mark.alpha_constitutional_gate
def test_resolve_invalid_candidate_fails(tmp_path):
    svc = _svc(tmp_path)
    understanding, decision = _understanding_and_decision()
    record = svc.create(understanding, decision, "s1", "u1", "req-1", "en", "corr-1")
    assert svc.resolve(
        record.clarification_id,
        session_id="s1",
        user_id="u1",
        correlation_id=record.correlation_id,
        version=record.version,
        selected_candidate_id="non-existent",
    ) is None


@pytest.mark.alpha_constitutional_gate
def test_resolve_replay_fails(tmp_path):
    svc = _svc(tmp_path)
    understanding, decision = _understanding_and_decision()
    record = svc.create(understanding, decision, "s1", "u1", "req-1", "en", "corr-1")
    cid = record.candidate_ids[0]
    assert svc.resolve(record.clarification_id, "s1", "u1", record.correlation_id, record.version, cid)
    assert svc.resolve(record.clarification_id, "s1", "u1", record.correlation_id, record.version, cid) is None


@pytest.mark.alpha_constitutional_gate
def test_cancel_executes_no_action(tmp_path):
    svc = _svc(tmp_path)
    understanding, decision = _understanding_and_decision()
    record = svc.create(understanding, decision, "s1", "u1", "req-1", "en", "corr-1")
    cancelled = svc.cancel(record.clarification_id, "s1", "u1", record.correlation_id, record.version)
    assert cancelled is not None
    assert cancelled.state == "cancelled"
    assert not cancelled.resolved_utterance


@pytest.mark.alpha_constitutional_gate
def test_none_of_these_executes_no_action(tmp_path):
    svc = _svc(tmp_path)
    understanding, decision = _understanding_and_decision()
    record = svc.create(understanding, decision, "s1", "u1", "req-1", "en", "corr-1")
    resolved = svc.resolve(record.clarification_id, "s1", "u1", record.correlation_id, record.version, "none")
    assert resolved is not None
    assert resolved.state == "cancelled"


@pytest.mark.alpha_constitutional_gate
def test_expired_resolution_fails(tmp_path, monkeypatch):
    svc = _svc(tmp_path)
    understanding, decision = _understanding_and_decision()
    record = svc.create(understanding, decision, "s1", "u1", "req-1", "en", "corr-1")
    record.expires_at = "2020-01-01T00:00:00+00:00"
    svc._store.put(record)
    assert svc.resolve(record.clarification_id, "s1", "u1", record.correlation_id, record.version, record.candidate_ids[0]) is None


@pytest.mark.alpha_constitutional_gate
def test_free_text_resolution(tmp_path):
    understanding = iu.resolve_input("borra ese archivo")
    understanding.requires_clarification = True
    decision = iu.make_decision(understanding)
    decision.ask_clarification = True
    svc = _svc(tmp_path)
    record = svc.create(understanding, decision, "s1", "u1", "req-1", "en", "corr-1")
    resolved = svc.resolve(
        record.clarification_id,
        session_id="s1",
        user_id="u1",
        correlation_id=record.correlation_id,
        version=record.version,
        free_text_response="el de descargas",
    )
    assert resolved is not None
    assert resolved.resolved_utterance == "el de descargas"


@pytest.mark.alpha_constitutional_gate
def test_stream_event_contains_no_secrets(tmp_path):
    svc = _svc(tmp_path)
    understanding = iu.resolve_input("borra el archivo con api key sk-12345")
    understanding.requires_clarification = True
    decision = iu.make_decision(understanding)
    decision.ask_clarification = True
    record = svc.create(understanding, decision, "s1", "u1", "req-1", "en", "corr-1")
    event = svc.to_stream_event(record)
    assert "sk-12345" not in str(event)
    assert event["type"] == "clarification"
    assert "options" in event


@pytest.mark.alpha_constitutional_gate
def test_supersede_pending_for_same_session(tmp_path):
    svc = _svc(tmp_path)
    understanding, decision = _understanding_and_decision()
    r1 = svc.create(understanding, decision, "s1", "u1", "req-1", "en", "corr-1")
    r2 = svc.create(understanding, decision, "s1", "u1", "req-2", "en", "corr-2")
    assert svc.get(r1.clarification_id).state == "superseded"
    assert svc.get(r2.clarification_id).state == "pending"


@pytest.mark.alpha_constitutional_gate
def test_persists_and_reloads_after_restart(tmp_path):
    svc = _svc(tmp_path)
    understanding, decision = _understanding_and_decision()
    record = svc.create(understanding, decision, "s1", "u1", "req-1", "en", "corr-1")
    # Simulate restart by creating a new store instance from the same file.
    svc2 = _svc(tmp_path)
    loaded = svc2.get(record.clarification_id)
    assert loaded is not None
    assert loaded.clarification_id == record.clarification_id
    assert loaded.state == "pending"
