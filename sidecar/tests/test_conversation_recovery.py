import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from repositories.database import DatabaseManager


@pytest.mark.alpha_constitutional_gate
class TestConversationRecovery:
    def test_pending_and_streaming_become_interrupted_on_startup(self):
        db = DatabaseManager()
        sid = f"recover-{uuid.uuid4().hex}"
        db.resolve_or_create_thread_v2("u1", sid, "Recovery")

        for state in ("pending", "streaming"):
            db.insert_conversation_message_v2({
                "user_id": "u1",
                "session_id": sid,
                "message_id": f"msg-{state}-{uuid.uuid4().hex}",
                "role": "assistant",
                "content": "",
                "completion_state": state,
                "correlation_id": f"corr-{state}",
            })

        completed = db.insert_conversation_message_v2({
            "user_id": "u1",
            "session_id": sid,
            "message_id": f"msg-completed-{uuid.uuid4().hex}",
            "role": "assistant",
            "content": "done",
            "completion_state": "completed",
            "correlation_id": "corr-completed",
        })

        cancelled = db.insert_conversation_message_v2({
            "user_id": "u1",
            "session_id": sid,
            "message_id": f"msg-cancelled-{uuid.uuid4().hex}",
            "role": "assistant",
            "content": "nope",
            "completion_state": "cancelled",
            "correlation_id": "corr-cancelled",
        })

        db._recover_interrupted_conversation_messages()

        messages = {m["correlation_id"]: m["completion_state"] for m in db.list_conversation_messages_v2("u1", sid)}
        assert messages["corr-pending"] == "interrupted"
        assert messages["corr-streaming"] == "interrupted"
        assert messages["corr-completed"] == "completed"
        assert messages["corr-cancelled"] == "cancelled"

    def test_interrupted_message_does_not_regenerate_automatically(self):
        db = DatabaseManager()
        sid = f"recover-no-regen-{uuid.uuid4().hex}"
        db.resolve_or_create_thread_v2("u1", sid, "Recovery")

        db.insert_conversation_message_v2({
            "user_id": "u1",
            "session_id": sid,
            "message_id": f"msg-{uuid.uuid4().hex}",
            "role": "assistant",
            "content": "partial",
            "completion_state": "streaming",
            "correlation_id": "corr-regen",
        })

        db._recover_interrupted_conversation_messages()

        row = db.list_conversation_messages_v2("u1", sid)[0]
        assert row["completion_state"] == "interrupted"
        assert "closed before this response completed" in row["interrupted_reason"]
        assert row["content"] == "partial"
