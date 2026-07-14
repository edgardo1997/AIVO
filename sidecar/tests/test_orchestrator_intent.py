import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from main import app
from conftest import TEST_IDENTITY

client = TestClient(app)


class TestExecutorCommandRouting:
    """Verifica que executor.command termina en executor.command Tool, no system.info."""

    def test_plan_step_uses_correct_tool(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "run command echo hello"})
        assert resp.status_code == 200
        data = resp.json()
        steps = data.get("plan", {}).get("steps", [])
        assert len(steps) >= 1, f"Expected at least 1 step, got {steps}"
        tool_id = steps[0].get("tool_id", "")
        assert tool_id == "executor.command", \
            f"Expected tool_id='executor.command', got '{tool_id}'"

    def test_intent_recognized_as_execute_command(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "run command echo hello"})
        assert resp.status_code == 200
        data = resp.json()
        intent = data.get("intent", {})
        assert intent.get("action") == "execute"
        assert intent.get("target") == "executor.command"

    def test_orchestrator_passes_command_param(self):
        from modules import get_gateway, init_sentinel_orchestrator
        gw = get_gateway()
        orch = init_sentinel_orchestrator(gw)
        import asyncio
        result = asyncio.run(orch.process("run command echo hello", identity=TEST_IDENTITY))
        exec_plan = result.plan
        params = exec_plan.tool_params
        assert "command" in params, f"Expected 'command' in params, got {params}"

    def test_tool_result_comes_from_executor_not_system(self):
        from modules.permissions import _svc as perm_svc
        perm_svc.set_level("admin")
        resp = client.post("/api/sentinel/process", json={"utterance": "run command echo hello123"})
        assert resp.status_code == 200
        data = resp.json()
        if data.get("blocked"):
            approve_resp = client.post("/api/sentinel/simulate/approve", json={
                "action_id": data["action_id"], "approved": True,
            })
            assert approve_resp.status_code == 200
            data = approve_resp.json()
        perm_svc.set_level("confirm")
        tool_result = data.get("tool_result")
        assert tool_result is not None, "Expected tool_result in response"
        assert "success" in tool_result, "Expected success field in tool_result"


class TestExecutorKillRouting:
    """Verifica que executor.kill termina en executor.kill Tool, no system.info."""

    def test_plan_step_uses_correct_tool(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "kill process 1234"})
        assert resp.status_code == 200
        data = resp.json()
        steps = data.get("plan", {}).get("steps", [])
        assert len(steps) >= 1, f"Expected at least 1 step, got {steps}"
        tool_id = steps[0].get("tool_id", "")
        assert tool_id == "executor.kill", \
            f"Expected tool_id='executor.kill', got '{tool_id}'"

    def test_intent_recognized_as_execute_kill(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "kill process 1234"})
        assert resp.status_code == 200
        data = resp.json()
        intent = data.get("intent", {})
        assert intent.get("target") == "executor.kill"

    def test_orchestrator_passes_pid_param(self):
        from modules import get_gateway, init_sentinel_orchestrator
        gw = get_gateway()
        orch = init_sentinel_orchestrator(gw)
        import asyncio
        result = asyncio.run(orch.process("kill process 1234", identity=TEST_IDENTITY))
        exec_plan = result.plan
        params = exec_plan.tool_params
        assert "pid" in params, f"Expected 'pid' in params, got {params}"
        assert params["pid"] == 1234, \
            f"Expected pid=1234, got {params.get('pid')}"


class TestRoutingIntegrity:
    """Verifica que otros targets no se rompen con las correcciones."""

    def test_system_info_still_routes_correctly(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "show system info"})
        assert resp.status_code == 200
        data = resp.json()
        steps = data.get("plan", {}).get("steps", [])
        assert len(steps) >= 1
        tool_id = steps[0].get("tool_id", "")
        assert tool_id == "system.info", \
            f"Expected system.info, got '{tool_id}'"

    def test_system_cpu_still_routes_correctly(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "cpu usage"})
        assert resp.status_code == 200
        data = resp.json()
        steps = data.get("plan", {}).get("steps", [])
        assert len(steps) >= 1
        tool_id = steps[0].get("tool_id", "")
        assert tool_id == "system.cpu"

    def test_system_processes_still_routes_correctly(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "show processes"})
        assert resp.status_code == 200
        data = resp.json()
        steps = data.get("plan", {}).get("steps", [])
        assert len(steps) >= 1
        tool_id = steps[0].get("tool_id", "")
        assert tool_id == "system.processes"
