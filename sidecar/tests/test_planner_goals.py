import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from sentinel.core.planner import Planner
from sentinel.core.intent import Intent
from sentinel.core.goals import GoalRegistry, GoalDefinition
from sentinel.core.capability_registry import RiskLevel


def make_goal(
    gid: str, intents: list = None, caps: list = None, priority: int = 0, risk: RiskLevel = RiskLevel.LOW
) -> GoalDefinition:
    return GoalDefinition(
        id=gid,
        name=gid.replace("_", " ").title(),
        description=f"Goal {gid}",
        related_intents=intents or [],
        possible_capabilities=caps or [],
        priority=priority,
        base_risk=risk,
    )


class TestPlannerGoalIntegration:
    def test_planner_without_goal_registry_unchanged(self):
        planner = Planner()
        intent = Intent(action="query", target="system.cpu")
        plan = planner.plan(intent)
        assert plan.goal is None

    def test_planner_with_goal_attaches_goal_to_plan(self):
        registry = GoalRegistry()
        registry.register(make_goal("diagnose", intents=["system.health"]))
        planner = Planner(goal_registry=registry)
        intent = Intent(action="query", target="system.health")
        plan = planner.plan(intent)
        assert plan.goal is not None
        assert plan.goal.id == "diagnose"

    def test_planner_goal_updates_description(self):
        registry = GoalRegistry()
        registry.register(make_goal("diagnose", intents=["system.health"]))
        planner = Planner(goal_registry=registry)
        intent = Intent(action="query", target="system.health")
        plan = planner.plan(intent)
        assert "Goal: Diagnose" in plan.description

    def test_planner_no_goal_match_still_works(self):
        registry = GoalRegistry()
        registry.register(make_goal("unrelated", intents=["other.intent"]))
        planner = Planner(goal_registry=registry)
        intent = Intent(action="query", target="system.cpu")
        plan = planner.plan(intent)
        assert plan.goal is None
        assert len(plan.steps) == 1

    def test_planner_goal_risk_raises_score(self):
        registry = GoalRegistry()
        registry.register(make_goal("risky", intents=["system.health"], risk=RiskLevel.CRITICAL))
        planner = Planner(goal_registry=registry)
        plan_no_goal = Planner().plan(Intent(action="query", target="system.health"))
        plan_with_goal = planner.plan(Intent(action="query", target="system.health"))
        assert plan_with_goal.risk_score > plan_no_goal.risk_score

    def test_planner_goal_with_low_risk_does_not_lower(self):
        registry = GoalRegistry()
        registry.register(make_goal("safe", intents=["executor.command"], risk=RiskLevel.LOW))
        planner = Planner(goal_registry=registry)
        intent = Intent(action="execute", target="executor.command")
        plan = planner.plan(intent)
        assert plan.risk_score > 0

    def test_goal_metadata_accessible_on_plan(self):
        registry = GoalRegistry()
        gd = make_goal(
            "cleanup",
            intents=["system.disk"],
            caps=["filesystem.list", "filesystem.write"],
            risk=RiskLevel.MEDIUM,
            priority=5,
        )
        registry.register(gd)
        planner = Planner(goal_registry=registry)
        plan = planner.plan(Intent(action="query", target="system.disk"))
        assert plan.goal.possible_capabilities == ["filesystem.list", "filesystem.write"]
        assert plan.goal.priority == 5
        assert plan.goal.base_risk == RiskLevel.MEDIUM


class TestPlannerGoalPriority:
    def test_highest_priority_goal_wins(self):
        registry = GoalRegistry()
        registry.register(make_goal("low_prio", intents=["system.health"], priority=1, risk=RiskLevel.LOW))
        registry.register(make_goal("high_prio", intents=["system.health"], priority=10, risk=RiskLevel.CRITICAL))
        planner = Planner(goal_registry=registry)
        plan = planner.plan(Intent(action="query", target="system.health"))
        assert plan.goal.id == "high_prio"


class TestPlannerGoalWithRegistryFallback:
    def test_goal_without_capability_falls_to_step_defs(self):
        registry = GoalRegistry()
        registry.register(make_goal("check", intents=["system.memory"]))
        planner = Planner(goal_registry=registry)
        plan = planner.plan(Intent(action="query", target="system.memory"))
        assert plan.goal is not None
        assert plan.goal.id == "check"
        assert len(plan.steps) == 1
        assert plan.steps[0].tool_id == "system.info"

    def test_goal_with_capability_prefers_capability(self):
        from sentinel.core.capability_registry import CapabilityRegistry, Capability, RiskLevel as RL

        cap_registry = CapabilityRegistry()
        cap_registry.register(
            Capability(
                id="system.cpu",
                name="CPU",
                description="CPU info",
                category="system",
                risk_level=RL.LOW,
                requires_confirmation=False,
                permissions=[],
                parameters={},
                result_type="json",
                tags=[],
                version="0.1.0",
                timeout_seconds=10,
            )
        )
        goal_registry = GoalRegistry()
        goal_registry.register(make_goal("monitor", intents=["system.cpu"]))
        planner = Planner(capability_registry=cap_registry, goal_registry=goal_registry)
        plan = planner.plan(Intent(action="query", target="system.cpu"))
        assert plan.goal is not None
        assert plan.goal.id == "monitor"
        assert plan.steps[0].tool_id == "system.cpu"


class TestPlannerGoalBackwardCompat:
    def test_existing_planner_tests_unaffected(self):
        planner = Planner()
        tests = [
            ("query", "system.cpu", 1, "system.cpu"),
            ("query", "system.memory", 1, "system.info"),
            ("query", "system.health", 4, None),
            ("execute", "executor.command", 1, "executor.command"),
        ]
        for action, target, steps, first_tool in tests:
            plan = planner.plan(Intent(action=action, target=target))
            assert len(plan.steps) == steps
            if first_tool:
                assert plan.steps[0].tool_id == first_tool
            assert plan.goal is None

    def test_goal_registry_empty_unchanged(self):
        registry = GoalRegistry()
        planner = Planner(goal_registry=registry)
        intent = Intent(action="query", target="system.cpu")
        plan = planner.plan(intent)
        assert plan.goal is None
        assert plan.steps[0].tool_id == "system.cpu"
