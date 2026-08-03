import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


@pytest.mark.alpha_constitutional_gate
class TestConversationExportAndDelete:
    def test_export_contains_sessions_without_secrets(self):
        session_id = "alpha-export-test"
        payload = {
            "messages": [
                {
                    "id": "m1",
                    "prompt": "Hello",
                    "response": "Hi there",
                    "provider": "sentinel_local",
                    "model": "Qwen3-1.7B-Q8_0.gguf",
                }
            ],
        }

        put_resp = client.put(f"/api/sentinel/conversations/{session_id}", json=payload)
        assert put_resp.status_code == 200

        export_resp = client.get("/api/sentinel/conversations/export")
        assert export_resp.status_code == 200
        data = export_resp.json()
        assert data["schema_version"] == "1.0"
        assert "exported_at" in data
        assert any(s["session_id"] == session_id for s in data["sessions"])
        # API keys / tokens must not be present in the export
        exported_text = json.dumps(data)
        assert "sk-" not in exported_text
        assert "Bearer " not in exported_text

        client.delete(f"/api/sentinel/conversations/{session_id}")

    @pytest.mark.alpha_constitutional_gate
    def test_delete_all_conversations(self):
        s1 = "alpha-delete-1"
        s2 = "alpha-delete-2"
        for sid, prompt in [(s1, "one"), (s2, "two")]:
            client.put(
                f"/api/sentinel/conversations/{sid}",
                json={"messages": [{"id": "m", "prompt": prompt, "response": "ok"}]},
            )

        before = client.get("/api/sentinel/conversations").json()
        assert any(s["session_id"] in (s1, s2) for s in before["conversations"])

        del_resp = client.delete("/api/sentinel/conversations")
        assert del_resp.status_code == 200
        assert del_resp.json()["deleted"] >= 2

        after = client.get("/api/sentinel/conversations").json()
        assert not any(s["session_id"] in (s1, s2) for s in after["conversations"])
