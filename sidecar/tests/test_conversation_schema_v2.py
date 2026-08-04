import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from repositories.database import DatabaseManager


@pytest.mark.alpha_constitutional_gate
class TestConversationSchemaV2:
    def test_v1_json_migrates_to_v2_and_is_idempotent(self, client):
        """A v1 JSON conversation is normalized into v2 tables and re-runs safely."""
        session_id = "alpha-schema-v2-migration"
        payload = {
            "messages": [
                {
                    "id": "m1",
                    "role": "user",
                    "content": "héllo ünïcöde",
                    "prompt": "héllo ünïcöde",
                    "provider": "openrouter",
                    "model": "gpt-4o",
                },
                {
                    "id": "m2",
                    "response": "Hi there",
                    "provider": "sentinel_local",
                    "model": "qwen3-1.7b",
                },
            ],
        }

        resp = client.put(f"/api/sentinel/conversations/{session_id}", json=payload)
        assert resp.status_code == 200

        db = DatabaseManager()
        conn = db._get_conn()

        db._migrate_conversations_v1_to_v2(conn)

        thread = conn.execute(
            "SELECT * FROM conversation_threads_v2 WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        assert thread is not None
        assert thread["schema_version"] == 2

        messages = conn.execute(
            """SELECT * FROM conversation_messages_v2
               WHERE session_id = ? ORDER BY sequence""",
            (session_id,),
        ).fetchall()
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "héllo ünïcöde"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["actual_provider"] == "sentinel_local"
        # Absent completion state must not be treated as completed.
        assert messages[1]["completion_state"] == "unknown"

        # Idempotency: re-run must not duplicate rows
        message_ids = [m["message_id"] for m in messages]
        db._migrate_conversations_v1_to_v2(conn)
        messages_after = conn.execute(
            "SELECT message_id FROM conversation_messages_v2 WHERE session_id = ?",
            (session_id,),
        ).fetchall()
        assert {m["message_id"] for m in messages_after} == set(message_ids)
