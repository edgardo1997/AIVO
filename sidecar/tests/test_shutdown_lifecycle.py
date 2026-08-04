import time
import uuid

import pytest

from modules.sentinel_lifecycle import SentinelLifecycle
from repositories.database import DatabaseManager


pytestmark = pytest.mark.alpha_constitutional_gate


@pytest.fixture(autouse=True)
def _reset_lifecycle():
    SentinelLifecycle.reset()
    yield
    SentinelLifecycle.reset()


def test_shutdown_is_idempotent():
    first = SentinelLifecycle.shutdown()
    assert first["status"] == "shutdown_complete"
    assert not first.get("already_done")

    second = SentinelLifecycle.shutdown()
    assert second["status"] == "already_shutdown"
    assert second["already_done"] is True


def test_database_connections_close_on_shutdown():
    db = DatabaseManager()
    conn = db._get_conn()
    assert conn is not None

    SentinelLifecycle.shutdown()

    # After shutdown, any new call must reopen a fresh connection.
    assert len(db._connections) == 0
    assert db.fetchone("SELECT 1") is not None


def test_shutdown_marks_in_flight_messages_interrupted():
    db = DatabaseManager()
    user_id = f"u-shutdown-{uuid.uuid4().hex}"
    session_id = "s-shutdown"
    db.insert_conversation_message_v2({
        "user_id": user_id,
        "session_id": session_id,
        "message_id": f"m-{uuid.uuid4().hex}",
        "role": "assistant",
        "content": "",
        "client_request_id": f"c-{uuid.uuid4().hex}",
        "completion_state": "streaming",
    })

    SentinelLifecycle.shutdown()

    rows = db.list_conversation_messages_v2(user_id, session_id)
    assert len(rows) == 1
    assert rows[0]["completion_state"] == "interrupted"


def test_model_router_and_provider_manager_close_called(monkeypatch):
    from unittest.mock import MagicMock

    router_cls = MagicMock()
    provider_cls = MagicMock()

    monkeypatch.setattr("sentinel.core.model_router.ModelRouter", router_cls)
    monkeypatch.setattr("sentinel.providers.provider_manager.ProviderManager", provider_cls)

    SentinelLifecycle.shutdown()

    router_cls.assert_called_once()
    router_cls.return_value.close.assert_called_once()
    provider_cls.assert_called_once()
    provider_cls.return_value.close.assert_called_once()


def test_shutdown_timeout_produces_truthful_warning(monkeypatch, caplog):
    db = DatabaseManager()

    def _slow_close(*args, **kwargs):
        time.sleep(0.1)

    monkeypatch.setattr(db, "close_connections", _slow_close)
    monkeypatch.setattr(db, "_recover_interrupted_conversation_messages", lambda: None)

    with caplog.at_level("WARNING"):
        result = SentinelLifecycle.shutdown(timeout=0.01)

    assert result["timeout_exceeded"] is True
    assert any("exceeding the" in r.message for r in caplog.records)


def test_shutdown_errors_do_not_leak_secrets_in_logs(monkeypatch, caplog):
    from unittest.mock import MagicMock

    secret = "sk-live-secret-12345"

    def _boom(*args, **kwargs):
        raise RuntimeError(f"failed with {secret}")

    monkeypatch.setattr("modules.sentinel_lifecycle.SentinelLifecycle._done", False)
    monkeypatch.setattr(DatabaseManager, "_recover_interrupted_conversation_messages", _boom)

    with caplog.at_level("ERROR"):
        SentinelLifecycle.shutdown()

    # The secret value should not appear in any log record.
    assert all(secret not in r.message for r in caplog.records)
    assert all(secret not in (r.exc_text or "") for r in caplog.records)


def test_database_restarts_without_corruption_after_shutdown():
    db = DatabaseManager()
    user_id = f"u-restart-{uuid.uuid4().hex}"
    db.upsert_conversation(user_id, "s1", "Before", [], _time())

    SentinelLifecycle.shutdown()

    db2 = DatabaseManager()
    row = db2.fetchone("SELECT * FROM conversation_threads WHERE user_id = ?", (user_id,))
    assert row is not None
    assert row["session_id"] == "s1"


def _time():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
