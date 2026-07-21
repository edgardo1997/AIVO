import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from types import SimpleNamespace
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


class TestChatPipeline:
    def test_governed_failure_cannot_be_rewritten_as_success(self):
        from modules.sentinel_bridge import _format_governed_outcome

        result = SimpleNamespace(
            plan=SimpleNamespace(intent=SimpleNamespace(confidence=0.9, target="executor.launch")),
            blocked=False,
            action_id=None,
            simulation_summary=None,
            error="app_name is required for executor.launch",
            tool_result=None,
        )

        message = _format_governed_outcome(result)
        assert message.startswith("No ejecuté")
        assert "required" in message

    def test_governed_confirmation_never_claims_execution(self):
        from modules.sentinel_bridge import _format_governed_outcome

        result = SimpleNamespace(
            plan=SimpleNamespace(intent=SimpleNamespace(confidence=0.9, target="executor.launch")),
            blocked=True,
            action_id="sim_once",
            simulation_summary="Requiere confirmación.",
            error="Execution blocked",
            tool_result=None,
        )

        assert _format_governed_outcome(result).startswith("Todavía no ejecuté")

    def test_conversation_only_stream_skips_expensive_orchestration(self, monkeypatch):
        from modules.ai_provider import _svc as ai_service
        from modules.sentinel_bridge import get_orchestrator

        async def orchestration_must_not_run(*_args, **_kwargs):
            raise AssertionError("Conversation-only requests must not run the execution pipeline")

        def deterministic_stream(**_kwargs):
            yield {"type": "delta", "text": "Una variable guarda un valor."}
            yield {"type": "done"}

        monkeypatch.setattr(get_orchestrator(), "process", orchestration_must_not_run)
        monkeypatch.setattr(ai_service, "stream_chat", deterministic_stream)
        response = client.post(
            "/api/sentinel/chat/stream",
            json={"message": "Explícame qué es una variable en Python"},
        )
        events = [json.loads(line) for line in response.text.splitlines() if line]
        pipeline = next(event for event in events if event["type"] == "pipeline")

        assert response.status_code == 200
        assert pipeline["route"] == "conversation"
        assert pipeline["planning_ms"] >= 0
        assert events[-1]["type"] == "done"

    def test_system_request_keeps_governed_pipeline(self, monkeypatch):
        from modules.ai_provider import _svc as ai_service

        def deterministic_stream(**_kwargs):
            yield {"type": "delta", "text": "Estado procesado"}
            yield {"type": "done"}

        monkeypatch.setattr(ai_service, "stream_chat", deterministic_stream)
        response = client.post(
            "/api/sentinel/chat/stream",
            json={"message": "Muestra el uso actual de CPU"},
        )
        events = [json.loads(line) for line in response.text.splitlines() if line]
        pipeline = next(event for event in events if event["type"] == "pipeline")

        assert response.status_code == 200
        assert pipeline["route"] == "governed"
        assert pipeline["pipeline"]["intent"]["target"] == "system.cpu"

    def test_conversation_history_can_be_saved_recovered_and_deleted(self):
        session_id = "conversation-persistence-test"
        payload = {
            "title": "Aprender Python",
            "messages": [
                {
                    "id": "message-1",
                    "prompt": "Enséñame variables",
                    "response": "Una variable guarda un valor.",
                    "provider": "sentinel_local",
                }
            ],
        }

        saved = client.put(f"/api/sentinel/conversations/{session_id}", json=payload)
        assert saved.status_code == 200
        assert saved.json()["messages"][0]["prompt"] == "Enséñame variables"

        listed = client.get("/api/sentinel/conversations")
        assert listed.status_code == 200
        assert session_id in {item["session_id"] for item in listed.json()["conversations"]}

        recovered = client.get(f"/api/sentinel/conversations/{session_id}")
        assert recovered.status_code == 200
        assert recovered.json()["title"] == "Aprender Python"

        deleted = client.delete(f"/api/sentinel/conversations/{session_id}")
        assert deleted.status_code == 200
        assert deleted.json()["deleted"] is True
        assert client.get(f"/api/sentinel/conversations/{session_id}").status_code == 404

    def test_conversation_history_validates_identifiers_and_payload_size(self):
        invalid = client.put("/api/sentinel/conversations/not%20valid", json={"messages": []})
        assert invalid.status_code == 422

        too_many = client.put(
            "/api/sentinel/conversations/too-many",
            json={"messages": [{"id": str(index), "prompt": "x"} for index in range(201)]},
        )
        assert too_many.status_code == 422

    def test_conversation_storage_is_isolated_by_user(self):
        from repositories.database import DatabaseManager

        db = DatabaseManager()
        db.upsert_conversation("user-a", "shared-id", "A", [], "2026-01-01T00:00:00+00:00")
        db.upsert_conversation("user-b", "shared-id", "B", [], "2026-01-01T00:00:01+00:00")

        assert db.get_conversation("user-a", "shared-id")["title"] == "A"
        assert db.get_conversation("user-b", "shared-id")["title"] == "B"
        assert db.delete_conversation("user-a", "shared-id") is True
        assert db.get_conversation("user-a", "shared-id") is None
        assert db.get_conversation("user-b", "shared-id")["title"] == "B"
        db.delete_conversation("user-b", "shared-id")

    def test_streaming_chat_emits_governed_progress_and_real_deltas(self, monkeypatch):
        from modules.ai_provider import _svc as ai_service

        def deterministic_stream(**_kwargs):
            yield {"type": "meta", "provider": "test-local", "model": "test-model"}
            yield {"type": "delta", "text": "Hola "}
            yield {"type": "delta", "text": "desde Sentinel"}
            yield {"type": "done"}

        monkeypatch.setattr(ai_service, "stream_chat", deterministic_stream)
        with client.stream(
            "POST",
            "/api/sentinel/chat/stream",
            json={"message": "explícame una variable en python", "session_id": "stream-test"},
        ) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("application/x-ndjson")
            events = [json.loads(line) for line in response.iter_lines() if line]

        event_types = [event["type"] for event in events]
        assert event_types[0] == "status"
        assert "pipeline" in event_types
        assert "meta" in event_types
        assert "metrics" in event_types
        assert event_types[-1] == "done"
        assert "".join(
            event["text"] for event in events if event["type"] == "delta"
        ) == "Hola desde Sentinel"
        stored = client.get("/api/sentinel/conversations/stream-test")
        assert stored.status_code == 200
        assert stored.json()["messages"][-1]["response"] == "Hola desde Sentinel"
        assert stored.json()["messages"][-1]["provider"] == "test-local"
        assert stored.json()["messages"][-1]["performance"]["output_tokens"] > 0
        client.delete("/api/sentinel/conversations/stream-test")

    def test_stream_inactivity_returns_clear_error(self, monkeypatch):
        from modules.ai_provider import _svc as ai_service
        import modules.sentinel_bridge as bridge

        stream_closed = []

        def stalled_stream(**_kwargs):
            try:
                time.sleep(0.1)
                yield {"type": "delta", "text": "demasiado tarde"}
            finally:
                stream_closed.append(True)

        monkeypatch.setattr(ai_service, "stream_chat", stalled_stream)
        monkeypatch.setattr(bridge, "_STREAM_IDLE_TIMEOUT_SECONDS", 0.01)
        response = client.post(
            "/api/sentinel/chat/stream",
            json={"message": "Explícame una lista en Python"},
        )
        events = [json.loads(line) for line in response.text.splitlines() if line]

        assert events[-1]["type"] == "error"
        assert events[-1]["detail"] == "stream_idle_timeout"
        deadline = time.time() + 1
        while not stream_closed and time.time() < deadline:
            time.sleep(0.01)
        assert stream_closed == [True]

    def test_stream_failure_returns_safe_provider_diagnosis(self, monkeypatch):
        from modules.ai_provider import _svc as ai_service

        def failed_stream(**_kwargs):
            raise RuntimeError("Provider sentinel_local interrupted the response")
            yield  # pragma: no cover - keeps this function a generator

        monkeypatch.setattr(ai_service, "stream_chat", failed_stream)
        response = client.post(
            "/api/sentinel/chat/stream",
            json={"message": "Explícame una función en Python"},
        )
        events = [json.loads(line) for line in response.text.splitlines() if line]
        failure = events[-1]

        assert failure["type"] == "error"
        assert failure["detail"] == "provider_interrupted"
        assert failure["provider"] == "sentinel_local"
        assert failure["retryable"] is True

    def test_interrupted_stream_preserves_partial_response(self, monkeypatch):
        from modules.ai_provider import _svc as ai_service

        def interrupted_stream(**_kwargs):
            yield {"type": "meta", "provider": "test-local", "model": "test-model"}
            yield {"type": "delta", "text": "Respuesta parcial"}

        monkeypatch.setattr(ai_service, "stream_chat", interrupted_stream)
        response = client.post(
            "/api/sentinel/chat/stream",
            json={"message": "prueba interrumpida", "session_id": "partial-stream"},
        )
        assert response.status_code == 200

        stored = client.get("/api/sentinel/conversations/partial-stream").json()
        assert stored["messages"][-1]["response"] == "Respuesta parcial"
        assert "interrumpida" in stored["messages"][-1]["error"]
        client.delete("/api/sentinel/conversations/partial-stream")

    def test_streaming_chat_rejects_empty_messages_inside_protocol(self):
        response = client.post("/api/sentinel/chat/stream", json={"message": "  "})
        assert response.status_code == 200
        events = [json.loads(line) for line in response.text.splitlines() if line]
        assert events == [{"type": "error", "message": "Please provide a message."}]

    def test_chat_endpoint_returns_response_shape(self):
        resp = client.post(
            "/api/sentinel/chat",
            json={
                "message": "show me cpu usage",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "response" in data
        assert len(data["response"]) > 0
        assert "pipeline" in data
        assert data["conversation_mode"] in ("advanced", "core")
        assert data["capabilities"]["conversation"]["available"] is True
        assert data["pipeline"]["intent"]["target"] == "system.cpu"

    def test_chat_with_conversational_message(self):
        resp = client.post(
            "/api/sentinel/chat",
            json={
                "message": "hello, how are you?",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "response" in data
        assert len(data["response"]) > 0
        assert data["pipeline"]["intent"]["confidence"] < 0.6

    def test_chat_with_empty_message(self):
        resp = client.post(
            "/api/sentinel/chat",
            json={
                "message": "",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["response"] == "Please provide a message."
        assert data["pipeline"] is None

    def test_chat_includes_pipeline_trace(self):
        resp = client.post(
            "/api/sentinel/chat",
            json={
                "message": "show my memory",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        trace = data["pipeline"]
        assert "intent" in trace
        assert "decision" in trace
        assert "tool_result" in trace
        assert "simulated" in trace
        assert "approved" in trace
        assert trace["intent"]["target"] in ("system.memory", "system.info")
        assert trace["presentation"]["mode"] == "user"
        assert trace["presentation"]["summary"]

    def test_chat_with_context_history(self):
        resp = client.post(
            "/api/sentinel/chat",
            json={
                "message": "and the disk too",
                "context": [
                    {"role": "user", "content": "show me cpu"},
                    {"role": "ai", "content": "CPU is at 23%"},
                ],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "response" in data

    def test_chat_with_session_id(self):
        resp = client.post(
            "/api/sentinel/chat",
            json={
                "message": "list processes",
                "session_id": "test-session-001",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "response" in data
        assert len(data["response"]) > 0

    def test_chat_actionable_intent_runs_tool(self):
        resp = client.post(
            "/api/sentinel/chat",
            json={
                "message": "what is my disk space",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["pipeline"]["tool_result"]["success"] is True
        assert data["pipeline"]["intent"]["confidence"] >= 0.6

    def test_chat_provider_and_model_included(self):
        resp = client.post(
            "/api/sentinel/chat",
            json={
                "message": "system status",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "provider" in data
        assert "model" in data

    def test_chat_multiple_quick_actions(self):
        actions = [
            "how is my pc doing",
            "show my system specs",
            "what's using the most cpu",
            "list my top processes",
        ]
        for msg in actions:
            resp = client.post("/api/sentinel/chat", json={"message": msg})
            assert resp.status_code == 200, f"Failed for: {msg}"
            data = resp.json()
            assert "response" in data
            assert len(data["response"]) > 0, f"Empty response for: {msg}"
