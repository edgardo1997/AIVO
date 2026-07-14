import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from main import app
from modules.sentinel_bridge import get_orchestrator, reset_bridge
from conftest import TEST_IDENTITY

client = TestClient(app)


class TestSimulationBlocking:
    def setup_method(self):
        reset_bridge()

    def test_low_risk_not_blocked(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "show system info"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["blocked"] is False
        assert data["action_id"] is None

    def test_high_risk_command_is_blocked(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "run command rm -rf /"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["blocked"] is True, f"Expected blocked=True, got {data.get('blocked')}"
        assert data["action_id"] is not None, "Expected action_id for blocked execution"
        assert data["error"] is not None, "Expected error message explaining block"
        assert "blocked" in data["error"].lower()
        assert data["simulation_summary"] != ""

    def test_blocking_pending_action_stored(self):
        orch = get_orchestrator()
        import asyncio

        result = asyncio.run(
            orch.process(
                "run command rm -rf /",
                identity=TEST_IDENTITY,
            )
        )
        assert result.blocked is True
        assert result.action_id is not None
        memory = orch._memory
        pending = memory.get_pending_action(result.action_id)
        assert pending is not None
        assert pending.params.get("utterance") == "run command rm -rf /"
        memory.remove_pending_action(result.action_id)

    def test_approve_execution_runs_and_succeeds(self):
        orch = get_orchestrator()
        import asyncio

        result = asyncio.run(
            orch.process(
                "run command echo hello_approved",
                identity=TEST_IDENTITY,
            )
        )
        assert result.blocked is True
        action_id = result.action_id

        from modules.permissions import _svc as perm_svc

        perm_svc.set_level("admin")
        approved = asyncio.run(orch.approve_execution(action_id, approved=True))
        perm_svc.set_level("confirm")

        assert approved.blocked is False
        assert approved.tool_result is not None
        assert approved.tool_result.success is True

    def test_reject_execution_returns_error(self):
        orch = get_orchestrator()
        import asyncio

        result = asyncio.run(
            orch.process(
                "run command echo should_reject",
                identity=TEST_IDENTITY,
            )
        )
        assert result.blocked is True
        action_id = result.action_id

        rejected = asyncio.run(orch.approve_execution(action_id, approved=False))
        assert rejected.blocked is False
        assert rejected.error is not None
        assert "rejected" in rejected.error.lower()

    def test_approve_unknown_action_returns_error(self):
        orch = get_orchestrator()
        import asyncio

        result = asyncio.run(orch.approve_execution("nonexistent_action", approved=True))
        assert result.error is not None
        assert "not found" in result.error.lower()

    def test_blocked_via_api_endpoint(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "run command rm -rf /"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["blocked"] is True

    def test_approve_reject_via_api_endpoint(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "run command echo api_test"})
        assert resp.status_code == 200
        data = resp.json()
        action_id = data["action_id"]

        reject_resp = client.post("/api/sentinel/simulate/reject", json={"action_id": action_id})
        assert reject_resp.status_code == 200
        reject_data = reject_resp.json()
        assert reject_data["blocked"] is False
        assert reject_data["approved"] is False

    def test_approve_then_execute_via_api(self):
        from modules.permissions import _svc as perm_svc

        perm_svc.set_level("admin")

        resp = client.post("/api/sentinel/process", json={"utterance": "run command echo api_approve"})
        assert resp.status_code == 200
        data = resp.json()
        action_id = data["action_id"]

        approve_resp = client.post(
            "/api/sentinel/simulate/approve",
            json={
                "action_id": action_id,
                "approved": True,
            },
        )
        perm_svc.set_level("confirm")
        assert approve_resp.status_code == 200
        approve_data = approve_resp.json()
        assert approve_data["blocked"] is False
        assert approve_data["tool_result"] is not None
        assert approve_data["tool_result"]["success"] is True

    def test_modify_and_approve_sends_modified_steps(self):
        from modules.permissions import _svc as perm_svc

        perm_svc.set_level("admin")

        resp = client.post("/api/sentinel/process", json={"utterance": "run command echo test_modified"})
        assert resp.status_code == 200
        data = resp.json()
        action_id = data["action_id"]
        assert action_id is not None

        plan_data = data.get("plan", {})
        steps = plan_data.get("steps", [])
        assert len(steps) > 0

        modify_resp = client.post(
            "/api/sentinel/simulate/modify-and-approve",
            json={
                "action_id": action_id,
                "steps": steps,
            },
        )
        perm_svc.set_level("confirm")
        assert modify_resp.status_code == 200
        modify_data = modify_resp.json()
        assert modify_data["modified"] is True
        assert modify_data["approved"] is False
        assert modify_data["requires_reconfirmation"] is True
        assert modify_data["action_id"] is not None
        assert modify_data["action_id"] != action_id
        assert modify_data["step_results"] is None

    def test_modify_and_approve_no_steps_returns_error(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "run command echo no_steps"})
        assert resp.status_code == 200
        data = resp.json()
        action_id = data["action_id"]

        modify_resp = client.post(
            "/api/sentinel/simulate/modify-and-approve",
            json={
                "action_id": action_id,
                "steps": [],
            },
        )
        modify_data = modify_resp.json() if modify_resp.status_code == 200 else modify_resp.json()
        assert modify_data.get("error") is not None or modify_data.get("detail") is not None

    def test_modify_and_approve_missing_action_id(self):
        modify_resp = client.post(
            "/api/sentinel/simulate/modify-and-approve",
            json={
                "steps": [{"tool_id": "system.info"}],
            },
        )
        assert modify_resp.status_code == 400

    def test_modify_and_approve_missing_steps(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "run command echo missing_steps"})
        assert resp.status_code == 200
        data = resp.json()
        action_id = data["action_id"]

        modify_resp = client.post(
            "/api/sentinel/simulate/modify-and-approve",
            json={
                "action_id": action_id,
            },
        )
        modify_data = modify_resp.json()
        assert modify_data.get("error") is not None
        assert "steps" in modify_data["error"].lower()

    def test_modify_and_approve_nonexistent_action(self):
        modify_resp = client.post(
            "/api/sentinel/simulate/modify-and-approve",
            json={
                "action_id": "nonexistent",
                "steps": [{"tool_id": "system.info"}],
            },
        )
        assert modify_resp.status_code == 200
        modify_data = modify_resp.json()
        assert modify_data["error"] is not None
        assert "not found" in modify_data["error"].lower()

    def test_chat_pipeline_trace_includes_blocked(self):
        from modules.permissions import _svc as perm_svc

        perm_svc.set_level("admin")
        resp = client.post("/api/sentinel/chat", json={"message": "delete everything"})
        perm_svc.set_level("confirm")
        assert resp.status_code == 200
        data = resp.json()
        pipeline = data.get("pipeline", {})
        assert "blocked" in pipeline
        assert "action_id" in pipeline
        assert "simulation_summary" in pipeline
