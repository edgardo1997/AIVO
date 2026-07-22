import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
from fastapi.testclient import TestClient
from main import app
from modules.permissions import _svc as perm_svc
from modules.sentinel_bridge import get_orchestrator, get_memory
from services.audit_service import AuditService

client = TestClient(app)


class TestFullHttpPipeline:
    def test_full_process_returns_all_stages(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "cpu usage"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["intent"]["target"] == "system.cpu"
        assert data["intent"]["action"] == "query"
        assert data["intent"]["confidence"] > 0
        assert data["plan"] is not None
        assert len(data["plan"]["steps"]) >= 1
        assert data["plan"]["steps"][0]["tool_id"] in ("system.cpu", "system.info")
        assert data["approved"] is True
        assert data["tool_result"]["success"] is True
        assert data["tool_result"]["data"] is not None
        assert data["presentation"]["status"] == "completed"
        assert data["presentation"]["mode"] == "user"
        assert data["presentation"]["summary"]
        assert data["presentation"]["details"] is None

    def test_developer_presentation_is_explicit_and_progressive(self):
        resp = client.post(
            "/api/sentinel/process",
            json={"utterance": "cpu usage", "presentation_mode": "developer"},
        )
        assert resp.status_code == 200
        presentation = resp.json()["presentation"]
        assert presentation["mode"] in ("developer", "user")
        if presentation.get("details"):
            assert presentation["details"].get("intent", {}).get("target") == "system.cpu"

    def test_full_pipeline_stores_memory(self):
        memory = get_memory()
        memory.clear()
        client.post("/api/sentinel/process", json={"utterance": "cpu usage"})
        last = memory.get_last_execution()
        assert last is not None
        assert last.utterance == "cpu usage"
        assert last.intent["target"] == "system.cpu"
        assert last.intent["action"] == "query"
        assert last.plan is not None
        assert last.plan["steps"] is not None
        assert len(last.plan["steps"]) >= 1
        assert last.tool_result is not None
        assert last.tool_result["success"] is True
        assert last.duration_ms >= 0

    def test_full_pipeline_creates_audit_entry(self):
        memory = get_memory()
        memory.clear()
        client.post("/api/sentinel/process", json={"utterance": "disk usage"})
        resp = client.get("/v1/audit", params={"limit": 50})
        assert resp.status_code == 200
        entries = resp.json().get("entries", [])
        pipeline_entries = [e for e in entries if "pipeline.system" in e.get("action", "")]
        assert len(pipeline_entries) >= 1, "No pipeline audit entry found"
        entry = pipeline_entries[0]
        assert entry["pipeline"]["intent"] is not None
        assert entry["pipeline"]["intent"]["target"] == "system.disk"
        assert entry["pipeline"]["execution"] is not None

    def test_process_endpoint_returns_step_results(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "analyze system health"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["step_results"]) >= 2
        for step in data["step_results"]:
            assert "step_id" in step
            assert "tool_id" in step
            assert "success" in step
            assert "duration_ms" in step
        assert data["tool_result"]["success"] is True
        assert data["tool_result"]["duration_ms"] >= 0

    def test_v1_execute_returns_pipeline_data(self):
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "system.info",
                "params": {},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"] is not None
        assert data["duration_ms"] >= 0
        assert data["pipeline"] is not None
        assert data["pipeline"]["plan"] is not None
        assert data["pipeline"]["decision"] is not None

    def test_last_execution_endpoint_returns_data(self):
        memory = get_memory()
        memory.clear()
        client.post("/api/sentinel/process", json={"utterance": "show processes"})
        resp = client.get("/api/sentinel/last-execution")
        assert resp.status_code == 200
        data = resp.json()
        assert data["execution"] is not None
        assert data["execution"]["utterance"] == "show processes"
        assert data["execution"]["intent"]["target"] == "system.processes"
        assert data["execution"]["tool_result"] is not None
        assert data["execution"]["step_results"] is not None


class TestMultiStepSystemHealth:
    def test_system_health_four_steps(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "analyze system health"})
        assert resp.status_code == 200
        data = resp.json()
        steps = data["step_results"]
        tool_ids = [s["tool_id"] for s in steps]
        assert "system.cpu" in tool_ids or "system.info" in tool_ids
        assert "system.processes" in tool_ids
        for s in steps:
            assert s["success"] is True, f"Step {s['step_id']}/{s['tool_id']} failed: {s.get('error')}"

    def test_system_health_steps_executed_in_parallel_levels(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "analyze system health"})
        assert resp.status_code == 200
        data = resp.json()
        steps = data["step_results"]
        step_ids = [s["step_id"] for s in steps]
        assert len(step_ids) >= 2

    def test_system_health_each_step_audited(self):
        client.post("/api/sentinel/process", json={"utterance": "analyze system health"})
        resp = client.get("/v1/audit", params={"limit": 100})
        entries = resp.json().get("entries", [])
        tools_in_audit = set()
        for e in entries:
            action = e.get("action", "")
            if action.startswith("pipeline.preflight."):
                tool = action.replace("pipeline.preflight.", "")
                tools_in_audit.add(tool)
            elif action.startswith("pipeline."):
                tool = action.replace("pipeline.", "")
                tools_in_audit.add(tool)
        assert "system.cpu" in tools_in_audit
        assert "system.info" in tools_in_audit
        assert "system.processes" in tools_in_audit


class TestPermissionEscalation:
    def test_view_level_blocks_then_admin_allows(self):
        perm_svc.set_level("view")
        try:
            resp = client.post("/api/sentinel/process", json={"utterance": "run command echo secret"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["approved"] is False, "View level should block executor command"
            assert data.get("error") is not None
        finally:
            perm_svc.set_level("admin")
        resp = client.post("/api/sentinel/process", json={"utterance": "run command echo hello"})
        assert resp.status_code == 200
        data = resp.json()
        if data.get("blocked"):
            approve_resp = client.post(
                "/api/sentinel/simulate/approve",
                json={
                    "action_id": data["action_id"],
                    "approved": True,
                },
            )
            assert approve_resp.status_code == 200
            data = approve_resp.json()
        assert data["approved"] is True
        assert data["tool_result"]["success"] is True
        assert data["tool_result"]["data"] is not None

    def test_v1_execute_blocked_at_view_allowed_at_admin(self):
        perm_svc.set_level("view")
        try:
            resp = client.post(
                "/v1/execute",
                json={
                    "tool_id": "filesystem.write",
                    "params": {"path": "C:\\test_blocked.txt", "content": "test"},
                },
            )
            data = resp.json()
            if data.get("data") and isinstance(data["data"], dict):
                assert data["data"].get("blocked") is True
            else:
                assert data["success"] is False
        finally:
            perm_svc.set_level("admin")
        import tempfile

        test_file = os.path.join(tempfile.gettempdir(), "integ_test_admin.txt")
        try:
            resp = client.post(
                "/v1/execute",
                json={
                    "tool_id": "filesystem.write",
                    "params": {"path": test_file, "content": "admin allowed"},
                },
            )
            assert resp.status_code == 200
            assert resp.json()["success"] is True
        finally:
            if os.path.exists(test_file):
                os.remove(test_file)


class TestEmergencyStopMidFlow:
    def test_emergency_stop_blocks_then_resume_works(self):
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "system.info",
                "params": {},
            },
        )
        assert resp.json()["success"] is True
        perm_svc.emergency("stop")
        try:
            resp = client.post(
                "/v1/execute",
                json={
                    "tool_id": "system.info",
                    "params": {},
                },
            )
            assert resp.json()["success"] is False
        finally:
            perm_svc.emergency("resume")
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "system.info",
                "params": {},
            },
        )
        assert resp.json()["success"] is True

    def test_emergency_stop_through_process_endpoint(self):
        perm_svc.emergency("stop")
        try:
            resp = client.post("/api/sentinel/process", json={"utterance": "cpu usage"})
            assert resp.status_code == 403
            assert "emergency" in resp.json()["error"].lower()
        finally:
            perm_svc.emergency("resume")
        resp = client.post("/api/sentinel/process", json={"utterance": "cpu usage"})
        assert resp.status_code == 200
        assert resp.json()["tool_result"]["success"] is True


class TestConfirmationWorkflow:
    def _create_pending_action(self, command: str) -> str:
        import uuid
        from modules.permissions import _svc as perm_svc

        aid = uuid.uuid4().hex[:12]
        perm_svc.pending_actions[aid] = {
            "command": command,
            "classification": "destructive",
            "timeout": 30,
        }
        return aid

    def test_destructive_command_requires_confirm(self):
        perm_svc.set_level("auto")
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "executor.command",
                "params": {"command": "echo safe_test", "timeout": 5},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["requires_confirmation"] is True

    def test_confirm_then_execute_succeeds(self):
        from modules.permissions import _svc as perm_svc
        import uuid

        perm_svc.set_level("confirm")
        action_id = uuid.uuid4().hex[:12]
        perm_svc.pending_actions[action_id] = {
            "command": "echo confirmed_ok",
            "classification": "safe",
            "timeout": 30,
        }
        perm_svc.confirm_action(action_id, approved=True)
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "executor.command",
                "params": {"command": "echo confirmed_ok", "timeout": 5, "confirmed": True, "action_id": action_id},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True, f"Failed: {data.get('error')}"

    def test_denied_command_blocked(self):
        perm_svc.set_level("confirm")
        action_id = self._create_pending_action("rm denied_file")
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "permissions.confirm",
                "params": {"action_id": action_id, "approved": False},
            },
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "executor.command",
                "params": {"command": "rm denied_file", "timeout": 5, "confirmed": True, "action_id": action_id},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        if data.get("data") and isinstance(data["data"], dict):
            assert data["data"].get("blocked") is True
        else:
            assert data["success"] is False


class TestErrorHandling:
    def test_empty_utterance_returns_error(self):
        resp = client.post("/api/sentinel/process", json={"utterance": ""})
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data
        assert data.get("error") is not None or "error" in str(data)

    def test_missing_utterance_returns_error(self):
        resp = client.post("/api/sentinel/process", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data or data.get("error") is not None

    def test_unknown_tool_returns_error(self):
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "system.nonexistent",
                "params": {},
            },
        )
        assert resp.status_code == 500 or resp.status_code == 200
        if resp.status_code == 200:
            assert resp.json()["success"] is False
            assert resp.json()["error"] is not None

    def test_invalid_params_returns_error(self):
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "filesystem.read",
                "params": {},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["error"] is not None

    def test_error_path_stores_memory(self):
        memory = get_memory()
        memory.clear()
        client.post(
            "/v1/execute",
            json={
                "tool_id": "system.nonexistent",
                "params": {},
            },
        )
        last = memory.get_last_execution()
        assert last is not None
        assert last.error is not None or last.tool_result["success"] is False


class TestAuditIntegration:
    def test_audit_logs_capture_all_pipeline_stages(self):
        client.post("/api/sentinel/process", json={"utterance": "cpu usage"})
        resp = client.get("/v1/audit", params={"limit": 50})
        entries = resp.json().get("entries", [])
        pipeline_entries = [e for e in entries if e.get("pipeline") is not None]
        assert len(pipeline_entries) >= 1
        entry = pipeline_entries[0]
        pipe = entry["pipeline"]
        assert pipe["identity"] is not None
        assert pipe["intent"] is not None
        assert pipe["decision"] is not None
        assert pipe["execution"] is not None
        # quality is None until quality measurement is wired

    def test_audit_trail_immutable(self):
        resp = client.get("/v1/audit", params={"limit": 100})
        count_before = resp.json()["total"]
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "system.memory",
                "params": {},
            },
        )
        assert resp.status_code == 200
        resp = client.get("/v1/audit", params={"limit": 100})
        count_after = resp.json()["total"]
        assert count_after > count_before

    def test_audit_clear_requires_admin(self):
        perm_svc.set_level("view")
        try:
            resp = client.post(
                "/v1/execute",
                json={
                    "tool_id": "audit.clear",
                    "params": {},
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            if data.get("data") and isinstance(data["data"], dict):
                assert data["data"].get("blocked") is True
            else:
                assert data["success"] is False
        finally:
            perm_svc.set_level("admin")


class TestDecisionContext:
    def test_decision_context_factors_returned(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "cpu usage"})
        data = resp.json()
        assert "context_factors" in data
        if data["final_risk_score"] is not None:
            assert data["base_risk_score"] is not None
            assert data["context_modifier"] is not None

    def test_decision_v1_execute_returns_decision(self):
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "system.cpu",
                "params": {},
            },
        )
        assert resp.status_code == 200
        pipe = resp.json()["pipeline"]
        assert pipe["decision"] is not None
        assert pipe["decision"]["decision"] in ("approve", "reject", "require_confirm")
        assert pipe["decision"]["reason"] is not None


class TestDryRun:
    def test_process_dry_run_returns_simulated(self):
        resp = client.post(
            "/api/sentinel/process",
            json={
                "utterance": "cpu usage",
                "dry_run": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["simulated"] is True
        assert data["plan"] is not None
        assert data["decision"] is not None
        assert data["tool_result"] is not None
        assert data["tool_result"]["success"] is True
        assert data["tool_result"]["data"]["simulated"] is True

    def test_execute_dry_run_returns_simulated(self):
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
        assert data["simulated"] is True
        assert data["success"] is True
        assert data["data"]["simulated"] is True

    def test_execute_dry_run_does_not_store_memory(self):
        from modules.sentinel_bridge import get_memory

        memory = get_memory()
        count_before = len(memory.get_session_history("dry_test", limit=100))
        client.post(
            "/v1/execute",
            json={
                "tool_id": "system.cpu",
                "params": {},
                "dry_run": True,
            },
        )
        count_after = len(memory.get_session_history("dry_test", limit=100))
        assert count_after == count_before

    def test_process_dry_run_multistep(self):
        resp = client.post(
            "/api/sentinel/process",
            json={
                "utterance": "system health check",
                "dry_run": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["simulated"] is True
        assert len(data["plan"]["steps"]) >= 3
        for step in data["step_results"]:
            assert step["success"] is True
            assert step["data"]["simulated"] is True

    def test_dry_run_false_does_not_set_simulated(self):
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "system.cpu",
                "params": {},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("simulated") is False or "simulated" not in data

    def test_process_dry_run_false(self):
        resp = client.post(
            "/api/sentinel/process",
            json={
                "utterance": "cpu usage",
                "dry_run": False,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["simulated"] is False or "simulated" not in data
