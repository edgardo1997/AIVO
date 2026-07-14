import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


class TestChatPipeline:
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
