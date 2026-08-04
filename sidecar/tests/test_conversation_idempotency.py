import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from repositories.database import DatabaseManager


@pytest.mark.alpha_constitutional_gate
class TestConversationIdempotency:
    @pytest.fixture(autouse=True)
    def db(self):
        return DatabaseManager()

    def test_user_message_stored_exactly_once(self, db):
        sid = f"idemp-user-{uuid.uuid4().hex}"
        db.resolve_or_create_thread_v2("u1", sid, "Test")

        result = db.insert_conversation_message_v2({
            "user_id": "u1",
            "session_id": sid,
            "message_id": f"msg-{uuid.uuid4().hex}",
            "role": "user",
            "content": "hello",
            "client_request_id": "req-1",
            "correlation_id": "corr-1",
            "requested_provider": "openrouter",
            "requested_model": "gpt-4o",
            "completion_state": "completed",
        })
        assert result.get("message_id")

        repeat = db.insert_conversation_message_v2({
            "user_id": "u1",
            "session_id": sid,
            "message_id": f"msg-{uuid.uuid4().hex}",
            "role": "user",
            "content": "different content",  # conflicting payload ignored
            "client_request_id": "req-1",
            "correlation_id": "corr-2",
            "requested_provider": "openrouter",
            "requested_model": "gpt-4o",
            "completion_state": "completed",
        })
        assert repeat["message_id"] == result["message_id"]

        messages = db.list_conversation_messages_v2("u1", sid)
        assert len(messages) == 1
        assert messages[0]["content"] == "hello"

    def test_duplicate_correlation_id_returns_existing_state(self, db):
        sid = f"idemp-corr-{uuid.uuid4().hex}"
        db.resolve_or_create_thread_v2("u1", sid, "Test")

        m1 = db.insert_conversation_message_v2({
            "user_id": "u1",
            "session_id": sid,
            "message_id": f"msg-{uuid.uuid4().hex}",
            "role": "user",
            "content": "first",
            "correlation_id": "corr-shared",
        })
        m2 = db.insert_conversation_message_v2({
            "user_id": "u1",
            "session_id": sid,
            "message_id": f"msg-{uuid.uuid4().hex}",
            "role": "user",
            "content": "second",
            "correlation_id": "corr-shared",
        })
        assert m1["message_id"] == m2["message_id"]
        assert db.list_conversation_messages_v2("u1", sid).__len__() == 1

    def test_assistant_finalized_exactly_once_and_terminal(self, db):
        sid = f"idemp-finalize-{uuid.uuid4().hex}"
        db.resolve_or_create_thread_v2("u1", sid, "Test")

        msg = db.insert_conversation_message_v2({
            "user_id": "u1",
            "session_id": sid,
            "message_id": f"msg-{uuid.uuid4().hex}",
            "role": "assistant",
            "content": "",
            "completion_state": "pending",
            "correlation_id": "corr-finalize",
        })

        ok1 = db.finalize_conversation_message_v2(
            "u1", sid, msg["message_id"],
            content="Hi there",
            actual_provider="sentinel_local",
            actual_model="qwen3-1.7b",
            completion_state="completed",
        )
        assert ok1 is True

        ok2 = db.finalize_conversation_message_v2(
            "u1", sid, msg["message_id"],
            content="overwritten",
            actual_provider="other",
            completion_state="completed",
        )
        # Completed is terminal; second finalization is a no-op.
        assert ok2 is False

        row = db.list_conversation_messages_v2("u1", sid)[0]
        assert row["content"] == "Hi there"
        assert row["actual_provider"] == "sentinel_local"
        assert row["completion_state"] == "completed"

    def test_failed_then_fallback_produces_one_completed_message(self, db):
        sid = f"idemp-fallback-{uuid.uuid4().hex}"
        db.resolve_or_create_thread_v2("u1", sid, "Test")

        assistant = db.insert_conversation_message_v2({
            "user_id": "u1",
            "session_id": sid,
            "message_id": f"msg-{uuid.uuid4().hex}",
            "role": "assistant",
            "content": "",
            "completion_state": "pending",
            "correlation_id": "corr-fallback",
            "requested_provider": "openrouter",
            "requested_model": "gpt-4o",
        })

        # First attempt failed.
        db.finalize_conversation_message_v2(
            "u1", sid, assistant["message_id"],
            completion_state="failed",
            error_category="provider_unavailable",
        )

        # Fallback succeeds and finalizes the same visible message.
        db.finalize_conversation_message_v2(
            "u1", sid, assistant["message_id"],
            content="I used the fallback.",
            actual_provider="sentinel_local",
            actual_model="qwen3-1.7b",
            completion_state="completed",
            fallback_required=1,
            fallback_reason="provider_unavailable",
        )

        messages = db.list_conversation_messages_v2("u1", sid)
        assert len(messages) == 1
        assert messages[0]["completion_state"] == "completed"
        assert messages[0]["actual_provider"] == "sentinel_local"
        assert messages[0]["fallback_required"] == 1
        assert messages[0]["fallback_reason"] == "provider_unavailable"

    def test_cancellation_writes_cancelled_and_rejects_completed(self, db):
        sid = f"idemp-cancel-{uuid.uuid4().hex}"
        db.resolve_or_create_thread_v2("u1", sid, "Test")

        assistant = db.insert_conversation_message_v2({
            "user_id": "u1",
            "session_id": sid,
            "message_id": f"msg-{uuid.uuid4().hex}",
            "role": "assistant",
            "content": "partial",
            "completion_state": "streaming",
            "correlation_id": "corr-cancel",
        })

        ok = db.finalize_conversation_message_v2(
            "u1", sid, assistant["message_id"],
            content="partial",
            completion_state="cancelled",
        )
        assert ok is True

        ok2 = db.finalize_conversation_message_v2(
            "u1", sid, assistant["message_id"],
            content="should not overwrite",
            completion_state="completed",
        )
        assert ok2 is False

        row = db.list_conversation_messages_v2("u1", sid)[0]
        assert row["completion_state"] == "cancelled"

    def test_unicode_and_large_content_survive(self, db):
        sid = f"idemp-unicode-{uuid.uuid4().hex}"
        db.resolve_or_create_thread_v2("u1", sid, "Test")

        content = "héllo ünïcöde ñoño " * 5000
        db.insert_conversation_message_v2({
            "user_id": "u1",
            "session_id": sid,
            "message_id": f"msg-{uuid.uuid4().hex}",
            "role": "user",
            "content": content,
            "correlation_id": "corr-unicode",
        })

        row = db.list_conversation_messages_v2("u1", sid)[0]
        assert row["content"] == content
