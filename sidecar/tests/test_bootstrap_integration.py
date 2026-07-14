import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import threading
import pytest
from fastapi.testclient import TestClient
from main import app
from conftest import TEST_IDENTITY

from modules import get_gateway, init_sentinel_orchestrator
from modules.sentinel_bridge import get_orchestrator, get_goal_registry, get_memory, reset_bridge
from sentinel.core.operational_memory import InMemoryBackend
from sentinel.core.goals import create_default_goal_registry
from sentinel.core.intent import Intent
from sentinel.core.planner import Planner

client = TestClient(app)


class TestBootstrapIntegration:
    def test_gateway_has_registered_tools(self):
        gw = get_gateway()
        specs = gw.list_specs()
        tool_ids = [s.id for s in specs]
        assert "system.cpu" in tool_ids
        assert "system.info" in tool_ids
        assert "executor.command" in tool_ids

    def test_capability_registry_public_property(self):
        orch = get_orchestrator()
        reg = orch.capability_registry
        assert reg is not None
        assert reg.get("system.cpu") is not None
        assert reg.get("system.info") is not None
        assert reg.get("nonexistent.cap") is None

    def test_orchestrator_processes_cpu_and_stores_memory(self):
        memory = InMemoryBackend()
        gw = get_gateway()
        registry = create_default_goal_registry()
        orch = init_sentinel_orchestrator(gw, memory=memory, goal_registry=registry)
        result = asyncio.run(orch.process("cpu usage", identity=TEST_IDENTITY))
        assert result.plan is not None
        assert result.plan.plan.goal is not None
        assert result.plan.plan.goal.id == "performance_tuning"
        last = memory.get_last_execution()
        assert last is not None
        assert last.utterance == "cpu usage"
        assert last.intent["target"] == "system.cpu"
        assert last.tool_result is not None

    def test_planner_works_with_default_registry(self):
        registry = create_default_goal_registry()
        planner = Planner(goal_registry=registry)
        plan = planner.plan(Intent(action="query", target="system.health"))
        assert plan.goal is not None
        assert plan.goal.id == "system_health_diagnosis"
        steps = plan.steps
        assert len(steps) == 4

    def test_bridge_singleton_initializes_once(self):
        reset_bridge()
        o1 = get_orchestrator()
        o2 = get_orchestrator()
        assert o1 is o2
        reg = get_goal_registry()
        assert reg is not None
        assert reg.count() >= 4
        mem = get_memory()
        assert mem is not None

    def test_bridge_singleton_thread_safe(self):
        reset_bridge()
        results = []

        def access():
            try:
                o = get_orchestrator()
                results.append(o)
            except Exception as e:
                results.append(e)

        threads = []
        for _ in range(10):
            t = threading.Thread(target=access, daemon=True)
            threads.append(t)
            t.start()
        for t in threads:
            t.join(timeout=5)
        assert len(results) == 10
        first = results[0]
        for r in results[1:]:
            assert r is first

    def test_goal_registry_from_bridge_matches_defaults(self):
        reset_bridge()
        reg = get_goal_registry()
        assert reg is None
        get_orchestrator()
        reg = get_goal_registry()
        for gid in ["system_health_diagnosis", "disk_space_cleanup", "network_diagnosis", "performance_tuning"]:
            goal = reg.get(gid)
            assert goal is not None
            assert isinstance(goal.context_rules, dict)

    def test_api_goal_matches_endpoint_with_bridge(self):
        reset_bridge()
        resp = client.get("/api/sentinel/goals/matches", params={"intent": "system.health"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["matches"]) >= 1
        assert data["matches"][0]["goal"] == "system_health_diagnosis"

    def test_full_bootstrap_lifecycle(self):
        memory = InMemoryBackend()
        gw = get_gateway()
        registry = create_default_goal_registry()
        orch = init_sentinel_orchestrator(gw, memory=memory, goal_registry=registry)
        result = asyncio.run(orch.process("analyze system health", identity=TEST_IDENTITY))
        assert result.approved
        assert result.plan.plan.goal.id == "system_health_diagnosis"
        assert len(result.step_results) >= 2
        last = memory.get_last_execution()
        assert last is not None
        assert last.step_results is not None
        assert len(last.step_results) >= 2
        assert last.tool_result is not None
