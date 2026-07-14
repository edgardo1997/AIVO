import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from main import app
from conftest import TEST_IDENTITY

from sentinel.core.operational_memory import InMemoryBackend, ExecutionRecord

client = TestClient(app)


def _create_orchestrator_with_memory():
    from modules import get_gateway, init_sentinel_orchestrator

    gw = get_gateway()
    memory = InMemoryBackend()
    orch = init_sentinel_orchestrator(gw, memory=memory)
    return orch, memory


class TestMemoryPipeline:
    def test_intent_plan_decision_stored(self):
        orch, memory = _create_orchestrator_with_memory()
        import asyncio

        asyncio.run(orch.process("cpu usage", identity=TEST_IDENTITY))
        last = memory.get_last_execution()
        assert last is not None
        assert last.utterance == "cpu usage"
        assert last.intent["target"] == "system.cpu"
        assert last.plan["risk_score"] >= 0

    def test_execution_has_duration(self):
        orch, memory = _create_orchestrator_with_memory()
        import asyncio

        asyncio.run(orch.process("show system info", identity=TEST_IDENTITY))
        last = memory.get_last_execution()
        assert last is not None
        assert last.duration_ms > 0

    def test_execution_has_timestamp(self):
        orch, memory = _create_orchestrator_with_memory()
        import asyncio

        asyncio.run(orch.process("cpu usage", identity=TEST_IDENTITY))
        last = memory.get_last_execution()
        assert last is not None
        assert "Z" in last.timestamp

    def test_execution_has_context_summary(self):
        orch, memory = _create_orchestrator_with_memory()
        import asyncio

        asyncio.run(orch.process("cpu usage", identity=TEST_IDENTITY))
        last = memory.get_last_execution()
        assert last is not None
        assert isinstance(last.context_summary, dict)

    def test_step_results_stored_for_multi_step(self):
        orch, memory = _create_orchestrator_with_memory()
        import asyncio

        asyncio.run(orch.process("analyze system health", identity=TEST_IDENTITY))
        last = memory.get_last_execution()
        assert last is not None
        assert len(last.step_results) >= 2

    def test_tool_result_in_memory(self):
        from modules.permissions import _svc as perm_svc

        orch, memory = _create_orchestrator_with_memory()
        perm_svc.set_level("admin")
        import asyncio

        asyncio.run(orch.process("run command echo hello", identity=TEST_IDENTITY))
        perm_svc.set_level("confirm")
        last = memory.get_last_execution()
        assert last is not None
        assert last.tool_result is not None

    def test_failed_execution_stored(self):
        orch, memory = _create_orchestrator_with_memory()
        import asyncio

        result = asyncio.run(orch.process("", identity=TEST_IDENTITY))
        last = memory.get_last_execution()
        if result.error:
            assert last is not None
            assert last.error is not None

    def test_orchestrator_exposes_get_last_execution(self):
        orch, memory = _create_orchestrator_with_memory()
        import asyncio

        asyncio.run(orch.process("cpu usage", identity=TEST_IDENTITY))
        last = orch.get_last_execution()
        assert last is not None
        assert last.utterance == "cpu usage"

    def test_orchestrator_without_memory_still_works(self):
        from modules import get_gateway, init_sentinel_orchestrator

        gw = get_gateway()
        orch = init_sentinel_orchestrator(gw)
        import asyncio

        result = asyncio.run(orch.process("cpu usage", identity=TEST_IDENTITY))
        assert result.plan is not None

    def test_multiple_executions_all_recorded(self):
        orch, memory = _create_orchestrator_with_memory()
        import asyncio

        asyncio.run(orch.process("cpu usage", identity=TEST_IDENTITY))
        asyncio.run(orch.process("show processes", identity=TEST_IDENTITY))
        asyncio.run(orch.process("disk usage", identity=TEST_IDENTITY))
        recent = memory.get_recent_executions(5)
        assert len(recent) == 3

    def test_last_execution_overwrites(self):
        orch, memory = _create_orchestrator_with_memory()
        import asyncio

        asyncio.run(orch.process("first", identity=TEST_IDENTITY))
        asyncio.run(orch.process("second", identity=TEST_IDENTITY))
        last = memory.get_last_execution()
        assert last.utterance == "second"

    def test_decision_in_memory(self):
        orch, memory = _create_orchestrator_with_memory()
        import asyncio

        asyncio.run(orch.process("run command echo hello", identity=TEST_IDENTITY))
        last = memory.get_last_execution()
        assert last is not None
        if last.decision is not None:
            assert "final_risk_score" in last.decision
            assert "context_modifier" in last.decision


class TestApiLastExecution:
    def test_get_last_execution_endpoint(self):
        client.post("/api/sentinel/process", json={"utterance": "cpu usage"})
        resp = client.get("/api/sentinel/last-execution")
        assert resp.status_code == 200
        data = resp.json()
        assert data["execution"] is not None
        assert data["execution"]["utterance"] == "cpu usage"

    def test_get_last_execution_content(self):
        client.post("/api/sentinel/process", json={"utterance": "analyze system health"})
        resp = client.get("/api/sentinel/last-execution")
        data = resp.json()
        exec_data = data["execution"]
        assert "execution_id" in exec_data
        assert "timestamp" in exec_data
        assert "intent" in exec_data
        assert "plan" in exec_data
        assert "step_results" in exec_data
        assert "duration_ms" in exec_data

    def test_get_last_execution_before_any_request(self):
        from fastapi.testclient import TestClient
        from main import app as main_app

        c = TestClient(main_app)
        resp = c.get("/api/sentinel/last-execution")
        assert resp.status_code == 200
        data = resp.json()
        assert data["execution"] is None or data["execution"]["utterance"] is not None

    def test_get_last_execution_has_context_summary(self):
        client.post("/api/sentinel/process", json={"utterance": "cpu usage"})
        resp = client.get("/api/sentinel/last-execution")
        data = resp.json()
        assert "context_summary" in data["execution"]
