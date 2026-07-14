import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from main import app

from modules.permissions import _svc as perm_svc
from sentinel.core.recovery import ErrorClassifier, ErrorCategory, RetryHandler, RecoveryPolicy

client = TestClient(app)


class TestHealthAndInfo:
    def test_health_endpoint(self):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_info_endpoint(self):
        resp = client.get("/api/info")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data
        assert "modules" in data


class TestProcessPipeline:
    def test_single_tool_cpu(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "cpu usage"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["intent"]["target"] == "system.cpu"
        steps = data["plan"]["steps"]
        assert len(steps) == 1
        assert steps[0]["tool_id"] == "system.cpu"
        assert data["tool_result"]["success"] is True
        assert "step_results" in data

    def test_single_tool_system_info(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "show system info"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["intent"]["target"] == "system.info"
        assert data["tool_result"]["success"] is True

    def test_multi_step_system_health(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "analyze system health"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["intent"]["target"] == "system.health"
        steps = data["plan"]["steps"]
        assert len(steps) >= 2
        tool_ids = [s["tool_id"] for s in steps]
        assert "system.cpu" in tool_ids
        assert "system.info" in tool_ids
        assert "system.processes" in tool_ids
        assert data["tool_result"]["success"] is True
        step_results = data.get("step_results")
        assert step_results is not None
        assert len(step_results) >= 2
        for sr in step_results:
            assert sr["success"] is True

    def test_risk_scores_present(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "analyze system health"})
        assert resp.status_code == 200
        data = resp.json()
        assert "base_risk_score" in data
        assert "context_modifier" in data
        assert "final_risk_score" in data

    def test_decision_fields_present(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "cpu usage"})
        assert resp.status_code == 200
        data = resp.json()
        assert "decision" in data
        assert "approved" in data
        assert data["decision"] in ("approve", "require_confirm", "reject")

    def test_spanish_utterance(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "mi pc esta lenta"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["intent"]["target"] == "system.health"

    def test_spanish_pesada(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "esta pesada la computadora"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["intent"]["target"] == "system.health"

    def test_processes_intent(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "show processes"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["intent"]["target"] == "system.processes"
        assert data["tool_result"]["success"] is True


class TestDryRunProcess:
    def test_dry_run_returns_plan_without_execution(self):
        resp = client.post("/api/sentinel/process", json={
            "utterance": "analyze system health", "dry_run": True,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["simulated"] is True
        assert data["tool_result"]["success"] is True
        tool_data = data["tool_result"].get("data", {})
        assert tool_data.get("simulated") is True
        steps = data["plan"]["steps"]
        assert len(steps) >= 2

    def test_dry_run_still_shows_intent_and_plan(self):
        resp = client.post("/api/sentinel/process", json={
            "utterance": "cpu usage", "dry_run": True,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["simulated"] is True
        assert data["intent"]["target"] == "system.cpu"
        assert len(data["plan"]["steps"]) == 1

    def test_dry_run_no_state_mutation(self):
        client.post("/api/sentinel/process", json={
            "utterance": "analyze system health", "dry_run": True,
        })
        last = client.get("/api/sentinel/last-execution")
        data = last.json()
        assert data["execution"] is None


class TestExecuteEndpoint:
    def test_execute_system_cpu(self):
        resp = client.post("/v1/execute", json={
            "tool_id": "system.cpu", "params": {},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "data" in data
        assert data["error"] is None

    def test_execute_system_info(self):
        resp = client.post("/v1/execute", json={
            "tool_id": "system.info", "params": {},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_execute_unknown_tool(self):
        resp = client.post("/v1/execute", json={
            "tool_id": "nonexistent.tool", "params": {},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False

    def test_execute_missing_tool_id_returns_422(self):
        resp = client.post("/v1/execute", json={"params": {}})
        assert resp.status_code == 422

    def test_execute_extra_fields_rejected(self):
        resp = client.post("/v1/execute", json={
            "tool_id": "system.cpu", "params": {}, "invalid_field": True,
        })
        assert resp.status_code == 422

    def test_execute_returns_pipeline_info(self):
        resp = client.post("/v1/execute", json={
            "tool_id": "system.cpu", "params": {},
        })
        data = resp.json()
        assert "pipeline" in data
        assert "plan" in data["pipeline"]
        assert "decision" in data["pipeline"]

    def test_execute_dry_run_simulated(self):
        resp = client.post("/v1/execute", json={
            "tool_id": "system.cpu", "params": {}, "dry_run": True,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["simulated"] is True
        tool_data = data.get("data", {})
        assert tool_data.get("simulated") is True

    def test_execute_app_discovery_list(self):
        resp = client.post("/v1/execute", json={
            "tool_id": "app.discovery", "params": {"action": "list"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "apps" in data["data"]

    def test_execute_app_discovery_capabilities(self):
        resp = client.post("/v1/execute", json={
            "tool_id": "app.discovery", "params": {"action": "capabilities"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        caps = data["data"]["capabilities"]
        assert len(caps) > 0
        ids = [c["id"] for c in caps]
        assert "system.cpu" in ids
        assert "app.discovery" in ids


class TestCapabilitiesEndpoint:
    def test_list_capabilities(self):
        resp = client.get("/api/sentinel/capabilities")
        assert resp.status_code == 200
        data = resp.json()
        assert "tools" in data
        assert len(data["tools"]) > 0
        tool_ids = [t["id"] for t in data["tools"]]
        assert "system.cpu" in tool_ids
        assert "system.info" in tool_ids
        assert "app.discovery" in tool_ids

    def test_capabilities_include_metadata(self):
        resp = client.get("/api/sentinel/capabilities")
        data = resp.json()
        tool = next(t for t in data["tools"] if t["id"] == "system.cpu")
        assert "name" in tool
        assert "description" in tool

    def test_capabilities_include_intents_and_models(self):
        resp = client.get("/api/sentinel/capabilities")
        data = resp.json()
        assert "intents" in data
        assert "models" in data


class TestGoalIntegration:
    def test_goals_endpoint(self):
        resp = client.get("/api/sentinel/goals")
        assert resp.status_code == 200
        data = resp.json()
        assert "goals" in data
        assert len(data["goals"]) > 0
        goal_ids = [g["id"] for g in data["goals"]]
        assert "system_health_diagnosis" in goal_ids

    def test_goal_matches_endpoint(self):
        resp = client.get("/api/sentinel/goals/matches", params={
            "intent": "system.health",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "matches" in data
        assert len(data["matches"]) > 0
        assert data["matches"][0]["goal"] == "system_health_diagnosis"

    def test_create_and_delete_goal(self):
        perm_svc.set_level("admin")
        new = client.post("/api/sentinel/goals", json={
            "id": "test_e2e_goal",
            "name": "E2E Test Goal",
            "description": "Temporary goal for E2E testing",
            "intent_targets": ["test.e2e"],
            "possible_capabilities": ["system.cpu"],
            "priority": 1,
            "base_risk": "low",
        })
        assert new.status_code == 201, f"Create failed: {new.text}"
        new_data = new.json()
        assert new_data["goal_id"] == "test_e2e_goal"
        found = client.get("/api/sentinel/goals/matches", params={"intent": "test.e2e"})
        assert found.status_code == 200
        assert any(m["goal"] == "test_e2e_goal" for m in found.json()["matches"])
        deleted = client.delete("/api/sentinel/goals/test_e2e_goal")
        assert deleted.status_code == 200
        after = client.get("/api/sentinel/goals/matches", params={"intent": "test.e2e"})
        assert not any(m["goal"] == "test_e2e_goal" for m in after.json()["matches"])
        perm_svc.set_level("confirm")


class TestSessionContinuity:
    def test_session_id_preserved_across_calls(self):
        session = "test-session-e2e"
        r1 = client.post("/api/sentinel/process", json={
            "utterance": "cpu usage", "session_id": session,
        })
        assert r1.status_code == 200
        last = client.get("/api/sentinel/last-execution")
        assert last.status_code == 200

    def test_different_sessions_isolated(self):
        r1 = client.post("/api/sentinel/process", json={
            "utterance": "cpu usage", "session_id": "session-a",
        })
        r2 = client.post("/api/sentinel/process", json={
            "utterance": "show system info", "session_id": "session-b",
        })
        assert r1.status_code == 200
        assert r2.status_code == 200


class TestPermissions:
    def test_admin_can_execute_command(self):
        perm_svc.set_level("admin")
        resp = client.post("/api/sentinel/process", json={
            "utterance": "run command echo hello",
        })
        assert resp.status_code == 200
        data = resp.json()
        if data.get("blocked"):
            approve_resp = client.post("/api/sentinel/simulate/approve", json={
                "action_id": data["action_id"], "approved": True,
            })
            assert approve_resp.status_code == 200
            data = approve_resp.json()
        assert data["tool_result"]["success"] is True
        perm_svc.set_level("confirm")

    def test_executor_command_returns_output(self):
        perm_svc.set_level("admin")
        resp = client.post("/v1/execute", json={
            "tool_id": "executor.command", "params": {"command": "echo hello"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["data"]["stdout"]) > 0
        perm_svc.set_level("confirm")


class TestRecoveryInPipeline:
    def test_process_pipeline_succeeds_without_errors(self):
        resp = client.post("/api/sentinel/process", json={
            "utterance": "analyze system health",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["error"] is None
        assert data["tool_result"]["success"] is True

    def test_step_results_all_successful(self):
        resp = client.post("/api/sentinel/process", json={
            "utterance": "analyze system health",
        })
        data = resp.json()
        step_results = data.get("step_results", [])
        for sr in step_results:
            assert sr["success"] is True

    def test_error_classifier_categorizes_errors(self):
        classifier = ErrorClassifier()
        for err in ["timeout", "connection refused", "permission denied"]:
            cat = classifier.classify(err)
            assert isinstance(cat, ErrorCategory)

    def test_retry_handler_uses_exponential_backoff(self):
        handler = RetryHandler()
        policy = RecoveryPolicy(max_retries=3, retry_delay_ms=100, retry_backoff=2.0)
        delays = []
        for attempt in range(1, policy.max_retries + 1):
            delay = min(policy.retry_delay_ms * (policy.retry_backoff ** (attempt - 1)),
                        policy.retry_max_delay_ms) / 1000
            delays.append(delay)
        assert len(delays) == 3
        for i in range(1, len(delays)):
            assert delays[i] >= delays[i - 1]
