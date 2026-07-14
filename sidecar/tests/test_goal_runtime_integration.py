import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from main import app

from sentinel.core.planner import Planner
from sentinel.core.intent import Intent
from sentinel.core.goals import (
    GoalRegistry,
    GoalDefinition,
    Goal,
    create_default_goal_registry,
)
from sentinel.core.capability_registry import RiskLevel

client = TestClient(app)


class TestDefaultGoalRegistry:
    def test_creates_system_health_diagnosis(self):
        registry = create_default_goal_registry()
        assert registry.count() == 4
        goal = registry.get("system_health_diagnosis")
        assert goal is not None
        assert goal.name == "System Health Diagnosis"

    def test_default_has_correct_intents(self):
        registry = create_default_goal_registry()
        goal = registry.get("system_health_diagnosis")
        assert "system.health" in goal.related_intents

    def test_default_has_capabilities(self):
        registry = create_default_goal_registry()
        goal = registry.get("system_health_diagnosis")
        assert "system.cpu" in goal.possible_capabilities
        assert "system.processes" in goal.possible_capabilities

    def test_default_priority(self):
        registry = create_default_goal_registry()
        goal = registry.get("system_health_diagnosis")
        assert goal.priority == 8
        assert goal.base_risk == RiskLevel.LOW

    def test_creates_disk_space_cleanup(self):
        registry = create_default_goal_registry()
        goal = registry.get("disk_space_cleanup")
        assert goal is not None
        assert goal.name == "Disk Space Cleanup"
        assert "system.disk" in goal.related_intents
        assert goal.priority == 5

    def test_creates_network_diagnosis(self):
        registry = create_default_goal_registry()
        goal = registry.get("network_diagnosis")
        assert goal is not None
        assert goal.name == "Network Diagnosis"
        assert "system.network" in goal.related_intents
        assert goal.priority == 6

    def test_creates_performance_tuning(self):
        registry = create_default_goal_registry()
        goal = registry.get("performance_tuning")
        assert goal is not None
        assert goal.name == "Performance Tuning"
        assert "system.cpu" in goal.related_intents
        assert "system.processes" in goal.related_intents
        assert "system.memory" in goal.related_intents
        assert goal.priority == 7

    def test_empty_registry_no_defaults(self):
        registry = GoalRegistry()
        assert registry.count() == 0


class TestPlannerWithGoalRegistry:
    def test_system_health_finds_goal(self):
        registry = create_default_goal_registry()
        planner = Planner(goal_registry=registry)
        plan = planner.plan(Intent(action="query", target="system.health"))
        assert plan.goal is not None
        assert plan.goal.id == "system_health_diagnosis"

    def test_goal_metadata_on_plan(self):
        registry = create_default_goal_registry()
        planner = Planner(goal_registry=registry)
        plan = planner.plan(Intent(action="query", target="system.health"))
        assert plan.goal.id == "system_health_diagnosis"
        assert plan.goal.priority == 8
        assert "system.cpu" in plan.goal.possible_capabilities

    def test_without_goal_registry_unchanged(self):
        planner = Planner()
        intent = Intent(action="query", target="system.health")
        plan = planner.plan(intent)
        assert plan.goal is None
        assert len(plan.steps) == 4

    def test_empty_goal_registry_unchanged(self):
        registry = GoalRegistry()
        planner = Planner(goal_registry=registry)
        intent = Intent(action="query", target="system.health")
        plan = planner.plan(intent)
        assert plan.goal is None
        assert len(plan.steps) == 4

    def test_existing_intents_unchanged(self):
        registry = create_default_goal_registry()
        planner = Planner(goal_registry=registry)
        for target, exp_steps, exp_tool in [
            ("system.cpu", 1, "system.cpu"),
            ("system.info", 1, "system.info"),
            ("system.memory", 1, "system.info"),
            ("executor.command", 1, "executor.command"),
            ("executor.kill", 2, "system.processes"),
        ]:
            plan = planner.plan(Intent(action="query", target=target))
            assert len(plan.steps) == exp_steps, f"{target} steps"
            assert plan.steps[0].tool_id == exp_tool, f"{target} tool_id"

    def test_steps_not_changed_by_goal(self):
        registry = create_default_goal_registry()
        planner = Planner(goal_registry=registry)
        plan_no = Planner().plan(Intent(action="query", target="system.health"))
        plan_yes = planner.plan(Intent(action="query", target="system.health"))
        assert [s.tool_id for s in plan_no.steps] == [s.tool_id for s in plan_yes.steps]


class TestMultiGoalPriority:
    def test_highest_priority_wins(self):
        registry = GoalRegistry()
        registry.register(
            GoalDefinition(
                id="low_prio",
                name="Low",
                description="",
                related_intents=["system.health"],
                possible_capabilities=["system.cpu"],
                priority=1,
                base_risk=RiskLevel.LOW,
            )
        )
        registry.register(
            GoalDefinition(
                id="high_prio",
                name="High",
                description="",
                related_intents=["system.health"],
                possible_capabilities=["system.info"],
                priority=10,
                base_risk=RiskLevel.HIGH,
            )
        )
        planner = Planner(goal_registry=registry)
        plan = planner.plan(Intent(action="query", target="system.health"))
        assert plan.goal.id == "high_prio"

    def test_multiple_goals_same_intent(self):
        registry = create_default_goal_registry()
        registry.register(
            GoalDefinition(
                id="extra_goal",
                name="Extra",
                description="",
                related_intents=["system.health"],
                possible_capabilities=["system.info"],
                priority=5,
                base_risk=RiskLevel.MEDIUM,
            )
        )
        planner = Planner(goal_registry=registry)
        plan = planner.plan(Intent(action="query", target="system.health"))
        assert plan.goal is not None


class TestGoalApiResponse:
    def test_api_returns_goal_for_health(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "analyze system health"})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("goal") is not None
        assert data["goal"]["id"] == "system_health_diagnosis"
        assert data["goal"]["priority"] == 8

    def test_api_goal_has_capabilities(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "analyze system health"})
        assert resp.status_code == 200
        data = resp.json()
        caps = data["goal"]["possible_capabilities"]
        assert "system.cpu" in caps
        assert "system.processes" in caps

    def test_api_goal_for_cpu_matches_performance_tuning(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "cpu usage"})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("goal") is not None
        assert data["goal"]["id"] == "performance_tuning"

    def test_api_goal_for_disk_matches_cleanup(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "disk usage"})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("goal") is not None
        assert data["goal"]["id"] == "disk_space_cleanup"

    def test_api_no_goal_for_uptime(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "system uptime"})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("goal") is None

    def test_api_no_goal_for_info(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "show system info"})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("goal") is None

    def test_api_goal_does_not_break_steps(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "analyze system health"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["plan"]["steps"]) >= 2

    def test_api_existing_intents_unaffected(self):
        for utterance, exp_tool in [
            ("cpu usage", "system.cpu"),
            ("show system info", "system.info"),
            ("run command echo hello", "executor.command"),
            ("kill process 1234", "executor.kill"),
        ]:
            resp = client.post("/api/sentinel/process", json={"utterance": utterance})
            assert resp.status_code == 200
            data = resp.json()
            steps = data["plan"]["steps"]
            assert len(steps) == 1
            assert steps[0]["tool_id"] == exp_tool


class TestInitSentinelOrchestrator:
    def test_old_call_without_goal_registry_works(self):
        from modules import get_gateway, init_sentinel_orchestrator

        gw = get_gateway()
        orch = init_sentinel_orchestrator(gw)
        assert orch is not None

    def test_with_goal_registry_attaches_goals(self):
        from modules import get_gateway, init_sentinel_orchestrator

        registry = create_default_goal_registry()
        gw = get_gateway()
        orch = init_sentinel_orchestrator(gw, goal_registry=registry)
        assert orch is not None


class TestFuzzyGoalMatching:
    def test_token_similarity_exact(self):
        sim = GoalRegistry._token_similarity("system.health", "system.health")
        assert sim == 1.0

    def test_token_similarity_partial(self):
        sim = GoalRegistry._token_similarity("health", "system.health")
        assert sim == 0.5

    def test_token_similarity_no_match(self):
        sim = GoalRegistry._token_similarity("disk", "system.health")
        assert sim == 0.0

    def test_search_exact_takes_precedence(self):
        registry = GoalRegistry()
        registry.register(
            GoalDefinition(
                id="test",
                name="Test",
                description="",
                related_intents=["custom.intent"],
                possible_capabilities=[],
                priority=0,
                base_risk=RiskLevel.LOW,
            )
        )
        exact = registry.find_by_intent("custom.intent")
        fuzzy = registry.search_by_intent("custom.intent")
        assert len(exact) == 1
        assert len(fuzzy) == 1
        assert fuzzy[0].id == "test"

    def test_search_fuzzy_finds_disk_from_disk(self):
        registry = create_default_goal_registry()
        results = registry.search_by_intent("disk")
        assert len(results) >= 1
        assert any(g.id == "disk_space_cleanup" for g in results)

    def test_search_fuzzy_finds_network_from_network(self):
        registry = create_default_goal_registry()
        results = registry.search_by_intent("network")
        assert len(results) >= 1
        assert any(g.id == "network_diagnosis" for g in results)

    def test_search_fuzzy_no_false_positive(self):
        registry = create_default_goal_registry()
        results = registry.search_by_intent("executor.command", threshold=0.4)
        assert len(results) == 0

    def test_search_fuzzy_empty_registry(self):
        registry = GoalRegistry()
        results = registry.search_by_intent("anything")
        assert results == []

    def test_planner_fuzzy_fallback_on_close_match(self):
        registry = GoalRegistry()
        registry.register(
            GoalDefinition(
                id="disk_goal",
                name="Disk Goal",
                description="",
                related_intents=["system.disk"],
                possible_capabilities=["system.info"],
                priority=5,
                base_risk=RiskLevel.LOW,
            )
        )
        planner = Planner(goal_registry=registry)
        plan = planner.plan(Intent(action="query", target="disk"))
        assert plan.goal is not None
        assert plan.goal.id == "disk_goal"

    def test_planner_fuzzy_not_triggered_on_exact_match(self):
        registry = create_default_goal_registry()
        planner = Planner(goal_registry=registry)
        plan = planner.plan(Intent(action="query", target="system.health"))
        assert plan.goal is not None
        assert plan.goal.id == "system_health_diagnosis"


class TestGoalsEndpoint:
    def test_get_goals_returns_list(self):
        resp = client.get("/api/sentinel/goals")
        assert resp.status_code == 200
        data = resp.json()
        assert "goals" in data
        assert isinstance(data["goals"], list)

    def test_get_goals_contains_health(self):
        resp = client.get("/api/sentinel/goals")
        data = resp.json()
        ids = [g["id"] for g in data["goals"]]
        assert "system_health_diagnosis" in ids

    def test_get_goals_contains_all_defaults(self):
        resp = client.get("/api/sentinel/goals")
        data = resp.json()
        ids = [g["id"] for g in data["goals"]]
        for expected in ["system_health_diagnosis", "disk_space_cleanup", "network_diagnosis", "performance_tuning"]:
            assert expected in ids, f"Missing goal: {expected}"

    def test_get_goals_has_metadata(self):
        resp = client.get("/api/sentinel/goals")
        data = resp.json()
        for g in data["goals"]:
            assert "id" in g
            assert "name" in g
            assert "description" in g
            assert "related_intents" in g
            assert "possible_capabilities" in g
            assert "priority" in g
            assert "base_risk" in g


class TestGoalRegistrySingleton:
    def test_get_goal_registry_returns_registry(self):
        from modules.sentinel_bridge import get_goal_registry

        registry = get_goal_registry()
        assert registry is not None
        assert registry.count() >= 4
        assert registry.get("system_health_diagnosis") is not None

    def test_get_goal_registry_has_default_goals(self):
        from modules.sentinel_bridge import get_goal_registry

        registry = get_goal_registry()
        for gid in ["system_health_diagnosis", "disk_space_cleanup", "network_diagnosis", "performance_tuning"]:
            goal = registry.get(gid)
            assert goal is not None, f"Missing {gid}"
