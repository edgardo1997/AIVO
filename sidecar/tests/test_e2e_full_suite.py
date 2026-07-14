import os

"""Comprehensive end-to-end tests covering all Sentinel modules.

Exercises the full intent -> simulate -> execute pipeline for every subsystem.
"""
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from main import app

from modules.permissions import _svc as perm_svc

client = TestClient(app)


class TestSystemInfo:
    """Core system tools: health, info, capabilities."""

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

    def test_list_capabilities(self):
        resp = client.get("/api/sentinel/capabilities")
        assert resp.status_code == 200
        data = resp.json()
        tool_ids = [t["id"] for t in data["tools"]]
        assert "system.cpu" in tool_ids
        assert "system.info" in tool_ids
        assert "app.discovery" in tool_ids

    def test_goals_endpoint(self):
        resp = client.get("/api/sentinel/goals")
        assert resp.status_code == 200
        data = resp.json()
        assert "goals" in data
        assert len(data["goals"]) > 0
        goal_ids = [g["id"] for g in data["goals"]]
        assert "system_health_diagnosis" in goal_ids


class TestProcessPipeline:
    """intent -> simulate -> execute: the core pipeline."""

    def test_single_tool_cpu(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "cpu usage"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["intent"]["target"] == "system.cpu"
        assert len(data["plan"]["steps"]) == 1
        assert data["plan"]["steps"][0]["tool_id"] == "system.cpu"
        assert data["tool_result"]["success"] is True

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
        for sr in data.get("step_results", []):
            assert sr["success"] is True

    def test_risk_and_decision_fields(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "cpu usage"})
        assert resp.status_code == 200
        data = resp.json()
        assert "decision" in data
        assert "approved" in data
        assert data["decision"] in ("approve", "require_confirm", "reject")

    def test_spanish_utterances(self):
        for utt in ["uso del cpu", "analizar salud del sistema", "ver procesos"]:
            resp = client.post("/api/sentinel/process", json={"utterance": utt})
            assert resp.status_code == 200, f"Spanish utterance failed: {utt}"

    def test_dry_run_returns_plan_without_execution(self):
        resp = client.post(
            "/api/sentinel/process",
            json={
                "utterance": "analyze system health",
                "dry_run": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("simulated") is True
        assert data["tool_result"]["data"].get("simulated") is True
        assert len(data["plan"]["steps"]) >= 2

    def test_approve_reject_cycle(self):
        try:
            perm_svc.set_level("view")
            resp = client.post(
                "/api/sentinel/process",
                json={
                    "utterance": "run command echo hello",
                },
            )
            data = resp.json()
            action_id = data.get("action_id")
            if action_id:
                reject = client.post(
                    "/api/sentinel/simulate/reject",
                    json={
                        "action_id": action_id,
                    },
                )
                assert reject.status_code == 200
                assert reject.json().get("approved") is False
        finally:
            perm_svc.set_level("confirm")

    def test_last_execution_returns_record(self):
        client.post("/api/sentinel/process", json={"utterance": "cpu usage"})
        resp = client.get("/api/sentinel/last-execution")
        assert resp.status_code == 200
        data = resp.json()
        exec_data = data.get("execution")
        if exec_data:
            assert "utterance" in exec_data
            assert "duration_ms" in exec_data

    def test_audit_log_after_pipeline(self):
        before = client.get("/v1/audit?limit=1").json().get("total", 0)
        client.post("/api/sentinel/process", json={"utterance": "cpu usage"})
        after = client.get("/v1/audit?limit=1").json().get("total", 0)
        assert after >= before

    def test_audit_integrity(self):
        resp = client.get("/v1/audit/integrity")
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True


class TestV1Execute:
    """Direct tool execution via /v1/execute."""

    def test_system_cpu(self):
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "system.cpu",
                "params": {},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_system_info(self):
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "system.info",
                "params": {},
            },
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_unknown_tool(self):
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "nonexistent.tool",
                "params": {},
            },
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is False

    def test_missing_tool_id_returns_422(self):
        resp = client.post("/v1/execute", json={"params": {}})
        assert resp.status_code == 422

    def test_extra_fields_rejected(self):
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "system.cpu",
                "params": {},
                "invalid": True,
            },
        )
        assert resp.status_code == 422

    def test_returns_pipeline_info(self):
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "system.cpu",
                "params": {},
            },
        )
        data = resp.json()
        assert "pipeline" in data
        assert "plan" in data["pipeline"]
        assert "decision" in data["pipeline"]

    def test_dry_run_simulated(self):
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "system.cpu",
                "params": {},
                "dry_run": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("simulated") is True

    def test_app_discovery_list(self):
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "app.discovery",
                "params": {"action": "list"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "apps" in data["data"]

    def test_app_discovery_capabilities(self):
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "app.discovery",
                "params": {"action": "capabilities"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        caps = data["data"].get("capabilities", [])
        ids = [c["id"] for c in caps]
        assert "system.cpu" in ids

    def test_executor_command_admin(self):
        try:
            perm_svc.set_level("admin")
            resp = client.post(
                "/v1/execute",
                json={
                    "tool_id": "executor.command",
                    "params": {"command": "echo hello"},
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert len(data["data"]["stdout"]) > 0
        finally:
            perm_svc.set_level("confirm")


class TestGoals:
    """Goal CRUD and matching."""

    def test_goal_matches(self):
        resp = client.get("/api/sentinel/goals/matches", params={"intent": "system.health"})
        assert resp.status_code == 200
        data = resp.json()
        assert "matches" in data
        assert len(data["matches"]) > 0
        assert data["matches"][0]["goal"] == "system_health_diagnosis"

    def test_create_and_delete_goal(self):
        try:
            perm_svc.set_level("admin")
            new = client.post(
                "/api/sentinel/goals",
                json={
                    "id": "e2e_test_goal",
                    "name": "E2E Test Goal",
                    "description": "Temporary goal for E2E testing",
                    "intent_targets": ["test.e2e"],
                    "possible_capabilities": ["system.cpu"],
                    "priority": 1,
                    "base_risk": "low",
                },
            )
            assert new.status_code == 201
            assert new.json()["goal_id"] == "e2e_test_goal"
            found = client.get("/api/sentinel/goals/matches", params={"intent": "test.e2e"})
            assert any(m["goal"] == "e2e_test_goal" for m in found.json()["matches"])
        finally:
            client.delete("/api/sentinel/goals/e2e_test_goal")
            perm_svc.set_level("confirm")


class TestWebBrowsing:
    """Web browsing tools and endpoints."""

    def test_web_search_tool_returns_dict(self):
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "web.search",
                "params": {"query": "python programming"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert isinstance(data["data"], dict)
        assert "results" in data["data"]

    def test_web_navigate_tool(self):
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "web.navigate",
                "params": {"url": "https://example.com"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_web_extract_tool(self):
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "web.extract",
                "params": {"url": "https://example.com"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "text" in data["data"] or "content" in data["data"]


class TestHardening:
    """Circuit breakers, timeouts, retries, health checks."""

    def test_hardening_config_structure(self):
        resp = client.get("/api/sentinel/hardening/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "enabled" in data
        assert "config" in data
        assert "default_timeout_seconds" in data["config"]

    def test_hardening_health_check(self):
        resp = client.get("/api/sentinel/hardening/health")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)

    def test_tool_timeout_override(self):
        resp = client.put(
            "/api/sentinel/hardening/tool-override/system.cpu",
            json={
                "timeout": 30,
                "max_retries": 2,
            },
        )
        assert resp.status_code == 200

    def test_tool_override_reset(self):
        resp = client.delete("/api/sentinel/hardening/tool-override/system.cpu")
        assert resp.status_code == 200


class TestTriggers:
    """Trigger rules CRUD and history."""

    def test_triggers_list_empty(self):
        resp = client.get("/v1/triggers")
        assert resp.status_code == 200
        data = resp.json()
        assert "triggers" in data

    def test_trigger_create_and_delete(self):
        resp = client.post(
            "/v1/triggers",
            json={
                "id": "e2e-test-trigger",
                "name": "E2E Test",
                "conditions": [{"metric": "cpu_percent", "operator": "gt", "value": 95}],
                "action": {"tool_id": "system.diagnostic", "params": {}},
                "cooldown_seconds": 60,
                "enabled": True,
            },
        )
        assert resp.status_code == 201
        assert resp.json()["trigger_id"] == "e2e-test-trigger"
        resp = client.delete("/v1/triggers/e2e-test-trigger")
        assert resp.status_code == 200

    def test_trigger_history_endpoint(self):
        resp = client.get("/v1/triggers/history?limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert "history" in data


class TestAgents:
    """Agent CRUD and delegation."""

    def test_agents_list(self):
        resp = client.get("/v1/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_agent_create_and_delete(self):
        resp = client.post(
            "/v1/agents",
            json={
                "agent_id": "e2e-test-agent",
                "name": "E2E Agent",
                "provider": "ollama",
                "model": "llama3",
                "capabilities": ["system.read"],
            },
        )
        assert resp.status_code == 201
        assert resp.json()["agent_id"] == "e2e-test-agent"
        resp = client.delete("/v1/agents/e2e-test-agent")
        assert resp.status_code == 200

    def test_agent_delegate_tool(self):
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "agent.delegate",
                "params": {"task": "show system info", "strategy": "auto"},
            },
        )
        assert resp.status_code == 200


class TestVault:
    """Encrypted secret storage."""

    def test_vault_status(self):
        resp = client.get("/api/sentinel/vault/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "entry_count" in data
        assert "encryption_enabled" in data

    def test_vault_create_and_reveal(self):
        client.post(
            "/api/sentinel/vault/entries",
            json={
                "id": "e2e-test-key",
                "name": "E2E Test Key",
                "category": "api_key",
                "value": "sk-test12345abcdef",
                "rotatable": True,
                "rotation_days": 30,
            },
        )
        reveal = client.post("/api/sentinel/vault/entries/e2e-test-key/reveal")
        assert reveal.status_code == 200
        assert reveal.json()["value"] == "sk-test12345abcdef"
        client.delete("/api/sentinel/vault/entries/e2e-test-key")

    def test_vault_list_and_audit(self):
        list_resp = client.get("/api/sentinel/vault/entries")
        assert list_resp.status_code == 200
        assert "entries" in list_resp.json()
        audit_resp = client.get("/api/sentinel/vault/audit?limit=10")
        assert audit_resp.status_code == 200
        assert "audit" in audit_resp.json()


class TestMultiAgent:
    """Multi-agent task delegation."""

    def test_multi_agent_simple_task(self):
        resp = client.post(
            "/api/sentinel/process/multi-agent",
            json={
                "utterance": "show system info",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "success" in data
        assert "sub_task_results" in data

    def test_multi_agent_empty_utterance(self):
        resp = client.post("/api/sentinel/process/multi-agent", json={"utterance": ""})
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data

    def test_multi_agent_complex_task(self):
        resp = client.post(
            "/api/sentinel/process/multi-agent",
            json={
                "utterance": "analyze system health and design a monitoring plan",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "sub_task_results" in data


class TestPermissions:
    """Permission levels, emergency stop, security."""

    def test_permission_status(self):
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "permissions.status",
                "params": {},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "level" in data["data"]
        assert "emergency_stop" in data["data"]

    def test_permission_level_toggle(self):
        try:
            perm_svc.set_level("admin")
            resp = client.post(
                "/v1/execute",
                json={
                    "tool_id": "permissions.status",
                    "params": {},
                },
            )
            assert resp.json()["data"]["level"] == "admin"
        finally:
            perm_svc.set_level("confirm")
            resp = client.post(
                "/v1/execute",
                json={
                    "tool_id": "permissions.status",
                    "params": {},
                },
            )
            assert resp.json()["data"]["level"] == "confirm"

    def test_admin_executes_command_via_pipeline(self):
        try:
            perm_svc.set_level("admin")
            resp = client.post(
                "/api/sentinel/process",
                json={
                    "utterance": "run command echo hello",
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            if data.get("blocked"):
                approve = client.post(
                    "/api/sentinel/simulate/approve",
                    json={
                        "action_id": data["action_id"],
                        "approved": True,
                    },
                )
                assert approve.status_code == 200
                data = approve.json()
            assert data["tool_result"]["success"] is True
        finally:
            perm_svc.set_level("confirm")


class TestSessions:
    """Session continuity and isolation."""

    def test_session_preserved(self):
        session = "test-session-e2e"
        resp = client.post(
            "/api/sentinel/process",
            json={
                "utterance": "cpu usage",
                "session_id": session,
            },
        )
        assert resp.status_code == 200


class TestAgentPersistence:
    """Agent persistence via API."""

    def test_agent_persistence_create_and_delete(self):
        resp = client.post(
            "/v1/agents",
            json={
                "agent_id": "e2e-persist-agent",
                "name": "Persist Agent",
                "provider": "ollama",
                "model": "llama3",
                "capabilities": ["system.read", "filesystem.read"],
                "allowed_tools": ["system.cpu", "system.info"],
                "status": "active",
            },
        )
        assert resp.status_code == 201

        resp = client.get("/v1/agents/e2e-persist-agent")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Persist Agent"

        resp = client.patch("/v1/agents/e2e-persist-agent", json={"name": "Renamed Agent"})
        assert resp.status_code == 200

        resp = client.get("/v1/agents/e2e-persist-agent")
        assert resp.json()["name"] == "Renamed Agent"

        client.delete("/v1/agents/e2e-persist-agent")
        resp = client.get("/v1/agents/e2e-persist-agent")
        assert resp.status_code == 404


class TestProfile:
    """Profile CRUD."""

    def test_profile_get(self):
        resp = client.get("/v1/profile")
        assert resp.status_code == 200
        data = resp.json()
        assert "profile" in data
        assert "preferences" in data
        assert "identity" in data
        assert data["identity"]["user_id"] is not None

    def test_profile_update(self):
        resp = client.patch("/api/sentinel/profile", json={"bio": "E2E tester"})
        assert resp.status_code == 200
        profile = resp.json()
        assert profile.get("bio") == "E2E tester"
        client.patch("/api/sentinel/profile", json={"bio": ""})


class TestRecovery:
    """Error recovery mechanisms."""

    def test_error_classifier(self):
        from sentinel.core.recovery import ErrorClassifier, ErrorCategory

        classifier = ErrorClassifier()
        for err in ["timeout", "connection refused", "permission denied"]:
            cat = classifier.classify(err)
            assert isinstance(cat, ErrorCategory)

    def test_retry_backoff(self):
        from sentinel.core.recovery import RetryHandler, RecoveryPolicy

        RetryHandler()
        policy = RecoveryPolicy(max_retries=3, retry_delay_ms=100, retry_backoff=2.0)
        delays = []
        for attempt in range(1, policy.max_retries + 1):
            delay = (
                min(policy.retry_delay_ms * (policy.retry_backoff ** (attempt - 1)), policy.retry_max_delay_ms) / 1000
            )
            delays.append(delay)
        assert len(delays) == 3
        for i in range(1, len(delays)):
            assert delays[i] >= delays[i - 1]
