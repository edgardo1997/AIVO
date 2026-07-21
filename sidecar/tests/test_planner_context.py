import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from main import app

from sentinel.core.planner import Planner
from sentinel.core.intent import Intent

client = TestClient(app)


class TestPlannerAcceptsContext:
    def test_plan_without_context_still_works(self):
        planner = Planner()
        intent = Intent(action="query", target="system.cpu", raw_input="cpu usage")
        plan = planner.plan(intent)
        assert len(plan.steps) == 1
        assert plan.steps[0].tool_id == "system.cpu"

    def test_plan_with_empty_context(self):
        planner = Planner()
        intent = Intent(action="query", target="system.cpu", raw_input="cpu usage")
        plan = planner.plan(intent, {})
        assert len(plan.steps) == 1

    def test_plan_with_context(self):
        planner = Planner()
        intent = Intent(action="query", target="system.cpu", raw_input="cpu usage")
        ctx = {"system_summary": {"cpu_percent": 95}}
        plan = planner.plan(intent, ctx)
        assert len(plan.steps) == 1


class TestSystemHealthMultiStep:
    def test_system_health_has_multiple_steps(self):
        planner = Planner()
        intent = Intent(action="query", target="system.health", raw_input="analyze system health")
        plan = planner.plan(intent)
        assert len(plan.steps) >= 2, f"Expected multiple steps, got {len(plan.steps)}"
        tool_ids = [s.tool_id for s in plan.steps]
        assert "system.cpu" in tool_ids
        assert "system.info" in tool_ids
        assert "system.processes" in tool_ids

    def test_system_health_risk_recalculated(self):
        planner = Planner()
        intent = Intent(action="query", target="system.health", raw_input="analyze system health")
        plan = planner.plan(intent)
        assert plan.risk_score > 0
        assert plan.description is not None

    def test_system_health_steps_have_correct_order(self):
        planner = Planner()
        intent = Intent(action="query", target="system.health", raw_input="analyze system health")
        plan = planner.plan(intent)
        steps = plan.steps
        assert steps[0].tool_id == "system.cpu"
        assert "system.info" in [s.tool_id for s in steps]
        assert steps[-1].tool_id == "system.processes"


class TestNormalIntentsUnchanged:
    def test_system_cpu_single_step(self):
        planner = Planner()
        intent = Intent(action="query", target="system.cpu", raw_input="cpu usage")
        plan = planner.plan(intent)
        assert len(plan.steps) == 1

    def test_system_info_single_step(self):
        planner = Planner()
        intent = Intent(action="query", target="system.info", raw_input="show system info")
        plan = planner.plan(intent)
        assert len(plan.steps) == 1

    def test_executor_command_single_step(self):
        planner = Planner()
        intent = Intent(action="execute", target="executor.command", raw_input="run command echo hello")
        plan = planner.plan(intent)
        assert len(plan.steps) == 1

    def test_executor_kill_two_steps(self):
        planner = Planner()
        intent = Intent(action="execute", target="executor.kill", raw_input="kill process 1234")
        plan = planner.plan(intent)
        assert len(plan.steps) == 2

    def test_system_processes_single_step(self):
        planner = Planner()
        intent = Intent(action="query", target="system.processes", raw_input="show processes")
        plan = planner.plan(intent)
        assert len(plan.steps) == 1


class TestPlanStepParams:
    def test_launch_parameters_are_preserved_and_catalog_evidence_is_explained(self):
        planner = Planner()
        intent = Intent(
            action="execute",
            target="executor.launch",
            parameters={"app_name": "Chrome", "elevated": False},
            raw_input="abre Chrome",
        )
        context = {
            "deep_context": {
                "installed_apps": [
                    {"name": "Chrome", "source": "app_paths", "confidence": 0.98}
                ]
            }
        }

        plan = planner.plan(intent, context)

        assert plan.steps[-1].params["app_name"] == "Chrome"
        assert plan.steps[-1].params["elevated"] is False
        assert "detected via app_paths" in plan.steps[-1].description
        assert "still requires policy authorization" in plan.steps[-1].description

    def test_unknown_application_is_not_claimed_as_installed(self):
        planner = Planner()
        intent = Intent(
            action="execute",
            target="executor.launch",
            parameters={"app_name": "Unknown App"},
        )

        plan = planner.plan(intent, {"deep_context": {"installed_apps": []}})

        assert "not confirmed" in plan.steps[-1].description

    def test_system_health_passes_limit_to_processes(self):
        planner = Planner()
        intent = Intent(action="query", target="system.health", parameters={"limit": 3}, raw_input="health check")
        plan = planner.plan(intent)
        procs_step = [s for s in plan.steps if s.tool_id == "system.processes"]
        assert len(procs_step) == 1
        assert procs_step[0].params.get("limit") == 5

    def test_custom_limit_with_context(self):
        planner = Planner()
        intent = Intent(action="query", target="system.health", raw_input="health check")
        ctx = {"system_summary": {"cpu_percent": 60}}
        plan = planner.plan(intent, ctx)
        assert len(plan.steps) >= 2


class TestIntegrationSystemHealth:
    def test_api_returns_multi_step_plan(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "analyze system health"})
        assert resp.status_code == 200
        data = resp.json()
        steps = data.get("plan", {}).get("steps", [])
        assert len(steps) >= 2, f"Expected multi-step plan, got {len(steps)} steps"

    def test_api_health_plan_includes_cpu(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "analyze system health"})
        assert resp.status_code == 200
        data = resp.json()
        tool_ids = [s["tool_id"] for s in data.get("plan", {}).get("steps", [])]
        assert "system.cpu" in tool_ids, f"Expected system.cpu in plan, got {tool_ids}"

    def test_api_health_plan_includes_info(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "analyze system health"})
        assert resp.status_code == 200
        data = resp.json()
        tool_ids = [s["tool_id"] for s in data.get("plan", {}).get("steps", [])]
        assert "system.info" in tool_ids

    def test_api_health_plan_includes_processes(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "analyze system health"})
        assert resp.status_code == 200
        data = resp.json()
        tool_ids = [s["tool_id"] for s in data.get("plan", {}).get("steps", [])]
        assert "system.processes" in tool_ids

    def test_api_intent_target_is_health(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "analyze system health"})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("intent", {}).get("target") == "system.health"

    def test_spansih_slow_triggers_health(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "mi pc esta lenta"})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("intent", {}).get("target") == "system.health"
        steps = data.get("plan", {}).get("steps", [])
        assert len(steps) >= 2

    def test_api_returns_risk_scores_with_health(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "analyze system health"})
        assert resp.status_code == 200
        data = resp.json()
        assert "base_risk_score" in data
        assert "context_modifier" in data
        assert "final_risk_score" in data

    def test_api_returns_step_results_with_health(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "analyze system health"})
        assert resp.status_code == 200
        data = resp.json()
        step_results = data.get("step_results")
        if step_results is not None:
            assert len(step_results) >= 2


class TestIntegrationRiskScoring:
    def test_api_risk_context_modifier_non_negative(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "cpu usage"})
        assert resp.status_code == 200
        data = resp.json()
        modifier = data.get("context_modifier")
        assert modifier is None or modifier >= 0

    def test_api_risk_fields_present(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "run command echo hello"})
        assert resp.status_code == 200
        data = resp.json()
        if data.get("decision") is not None:
            assert "base_risk_score" in data
            assert "context_modifier" in data
            assert "final_risk_score" in data


class TestBackwardCompatUnchanged:
    def test_executor_command_single_step(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "run command echo hello"})
        assert resp.status_code == 200
        data = resp.json()
        steps = data.get("plan", {}).get("steps", [])
        assert len(steps) == 1
        assert steps[0]["tool_id"] == "executor.command"

    def test_executor_kill_single_step(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "kill process 1234"})
        assert resp.status_code == 200
        data = resp.json()
        steps = data.get("plan", {}).get("steps", [])
        assert len(steps) == 1
        assert steps[0]["tool_id"] == "executor.kill"

    def test_system_info_single_step(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "show system info"})
        assert resp.status_code == 200
        data = resp.json()
        steps = data.get("plan", {}).get("steps", [])
        assert len(steps) == 1
        assert steps[0]["tool_id"] == "system.info"

    def test_system_cpu_single_step(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "cpu usage"})
        assert resp.status_code == 200
        data = resp.json()
        steps = data.get("plan", {}).get("steps", [])
        assert len(steps) == 1

    def test_tool_result_still_present(self):
        client.post("/api/permissions/level", json={"level": "admin"})
        resp = client.post("/api/sentinel/process", json={"utterance": "run command echo hello"})
        client.post("/api/permissions/level", json={"level": "confirm"})
        assert resp.status_code == 200
        data = resp.json()
        assert "tool_result" in data
