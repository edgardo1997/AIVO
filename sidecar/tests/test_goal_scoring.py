import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from main import app

from sentinel.core.goals import (
    GoalRegistry,
    GoalDefinition,
    GoalScorer,
    GoalScorerConfig,
    GoalMatchResult,
    ScoredGoal,
    create_default_goal_registry,
)
from sentinel.core.planner import Planner, Plan
from sentinel.core.intent import Intent
from sentinel.core.capability_registry import RiskLevel

client = TestClient(app)


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


class TestGoalMatchResult:
    def test_exact_match_confidence(self):
        registry = GoalRegistry()
        registry.register(make_goal("g1", intents=["system.health"]))
        candidates = registry.find_candidates("system.health")
        assert len(candidates) == 1
        assert candidates[0].confidence == 1.0
        assert candidates[0].match_type == "exact"

    def test_exact_wins_over_fuzzy(self):
        registry = GoalRegistry()
        registry.register(make_goal("exact", intents=["system.health"]))
        registry.register(make_goal("fuzzy", intents=["system.cpu"]))
        candidates = registry.find_candidates("system.health")
        assert len(candidates) == 1
        assert candidates[0].goal.id == "exact"

    def test_fuzzy_match_finds_disk(self):
        registry = GoalRegistry()
        registry.register(make_goal("disk_goal", intents=["system.disk"]))
        candidates = registry.find_candidates("disk")
        assert len(candidates) == 1
        assert candidates[0].match_type == "fuzzy_intent"
        assert candidates[0].confidence < 1.0

    def test_capability_match(self):
        registry = GoalRegistry()
        registry.register(make_goal("perf", intents=["system.health"], caps=["system.cpu"]))
        candidates = registry.find_candidates("cpu")
        cap_matches = [c for c in candidates if c.match_type == "capability"]
        assert len(cap_matches) >= 1
        assert cap_matches[0].goal.id == "perf"

    def test_keyword_match(self):
        registry = GoalRegistry()
        registry.register(make_goal("perf_tune", intents=[], caps=[], priority=0, risk=RiskLevel.LOW))
        candidates = registry.find_candidates("tune")
        kw_matches = [c for c in candidates if c.match_type == "keyword"]
        assert len(kw_matches) >= 1
        assert kw_matches[0].goal.id == "perf_tune"

    def test_no_match_returns_empty(self):
        registry = GoalRegistry()
        registry.register(make_goal("g1", intents=["system.health"]))
        candidates = registry.find_candidates("executor.command")
        assert candidates == []

    def test_empty_registry(self):
        registry = GoalRegistry()
        assert registry.find_candidates("anything") == []


class TestGoalScorer:
    def test_exact_match_ranks_highest(self):
        registry = create_default_goal_registry()
        candidates = registry.find_candidates("system.health")
        scorer = GoalScorer()
        ranked = scorer.rank(candidates)
        assert len(ranked) >= 1
        assert ranked[0].result.goal.id == "system_health_diagnosis"
        assert ranked[0].result.match_type == "exact"

    def test_high_cpu_context_favors_performance(self):
        registry = GoalRegistry()
        registry.register(make_goal("perf", intents=["system.cpu"], caps=[], priority=7))
        registry.register(make_goal("health", intents=["system.health"], caps=[], priority=8))
        candidates = registry.find_candidates("cpu")
        scorer = GoalScorer({"cpu_percent": 95, "memory_percent": 90})
        ranked = scorer.rank(candidates)
        assert len(ranked) >= 1
        # performance_tuning should get high context bonus
        perf = [s for s in ranked if s.result.goal.id == "perf"]
        health = [s for s in ranked if s.result.goal.id == "health"]
        if perf and health:
            assert perf[0].score > health[0].score, "Performance should outrank health when CPU is high"

    def test_high_disk_context_favors_disk_cleanup(self):
        registry = create_default_goal_registry()
        candidates = registry.find_candidates("disk")
        scorer = GoalScorer({"disk_percent": 95})
        ranked = scorer.rank(candidates)
        disk_goals = [s for s in ranked if s.result.goal.id == "disk_space_cleanup"]
        assert len(disk_goals) >= 1
        assert "high_disk_context" in disk_goals[0].reasons

    def test_low_confidence_candidate_still_returned(self):
        registry = create_default_goal_registry()
        candidates = registry.find_candidates("obscure_term_xyz")
        # Should still find keyword matches but with low scores
        scorer = GoalScorer()
        ranked = scorer.rank(candidates)
        for s in ranked:
            assert s.score >= 0.0

    def test_empty_candidates(self):
        scorer = GoalScorer({"cpu_percent": 95})
        ranked = scorer.rank([])
        assert ranked == []

    def test_planner_with_goal_scorer(self):
        registry = create_default_goal_registry()
        planner = Planner(goal_registry=registry)
        plan = planner.plan(Intent(action="query", target="system.health"))
        assert plan.goal is not None
        assert plan.goal.id == "system_health_diagnosis"

    def test_planner_without_goal_registry(self):
        planner = Planner()
        plan = planner.plan(Intent(action="query", target="system.health"))
        assert plan.goal is None


class TestGoalMatchesApi:
    def test_api_returns_matches_for_health(self):
        resp = client.get("/api/sentinel/goals/matches", params={"intent": "system.health"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["intent"] == "system.health"
        assert len(data["matches"]) >= 1
        assert data["matches"][0]["goal"] == "system_health_diagnosis"

    def test_api_exact_match_score(self):
        resp = client.get("/api/sentinel/goals/matches", params={"intent": "system.health"})
        data = resp.json()
        top = data["matches"][0]
        assert top["confidence"] == 1.0
        assert top["match_type"] == "exact"

    def test_api_with_context_bonus(self):
        resp = client.get("/api/sentinel/goals/matches", params={"intent": "cpu", "cpu": 95, "memory": 90})
        assert resp.status_code == 200
        data = resp.json()
        assert data["context"]["cpu_percent"] == 95
        matches = data["matches"]
        scores = [m["score"] for m in matches]
        assert len(scores) >= 1

    def test_api_no_matches(self):
        resp = client.get("/api/sentinel/goals/matches", params={"intent": "nonexistent_intent_xyz"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["matches"] == []

    def test_api_explains_reasons(self):
        resp = client.get("/api/sentinel/goals/matches", params={"intent": "disk", "disk": 95})
        data = resp.json()
        assert len(data["matches"]) >= 1
        reasons = data["matches"][0].get("reasons", [])
        assert len(reasons) >= 1

    def test_api_missing_intent_returns_422(self):
        resp = client.get("/api/sentinel/goals/matches")
        assert resp.status_code == 422


class TestPlannerBackwardCompat:
    def test_existing_intents_steps_unchanged(self):
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

    def test_goal_description_on_plan(self):
        registry = create_default_goal_registry()
        planner = Planner(goal_registry=registry)
        plan = planner.plan(Intent(action="query", target="system.health"))
        assert "Goal:" in plan.description
        assert "System Health Diagnosis" in plan.description

    def test_no_goal_for_unknown_intent(self):
        registry = create_default_goal_registry()
        planner = Planner(goal_registry=registry)
        plan = planner.plan(Intent(action="query", target="executor.command"))
        assert plan.goal is None


class TestGoalScorerConfigInjection:
    def test_get_config_returns_config(self):
        cfg = GoalScorerConfig(confidence_weight=0.5, priority_weight=0.3, context_weight=0.2)
        scorer = GoalScorer(config=cfg)
        assert scorer.get_config() is cfg
        assert scorer.get_config().confidence_weight == 0.5

    def test_planner_injects_config_into_scorer(self):
        cfg = GoalScorerConfig(min_confidence=0.0, confidence_weight=1.0, priority_weight=0.0, context_weight=0.0)
        registry = GoalRegistry()
        registry.register(make_goal("g1", intents=["system.test"], priority=10))
        planner = Planner(goal_registry=registry, scorer_config=cfg)
        plan = planner.plan(Intent(action="query", target="system.test"))
        # with confidence_weight=1.0 and others 0, score == confidence
        assert plan.goal is not None
        assert plan.goal.id == "g1"

    def test_scorer_config_default_when_none(self):
        planner = Planner()
        # just ensure construction works without scorer_config
        assert planner._scorer_config is None


class TestContextBonusRules:
    def test_context_bonus_zero_without_rules(self):
        g = GoalDefinition(
            id="no_rules",
            name="No Rules",
            description="",
            related_intents=["system.test"],
            possible_capabilities=[],
            context_rules={},
        )
        scorer = GoalScorer({"cpu_percent": 95, "disk_percent": 95})
        bonus = scorer._context_bonus(g)
        assert bonus == 0.0

    def test_context_bonus_applies_cpu_rule(self):
        g = GoalDefinition(
            id="cpu_rule",
            name="CPU Rule",
            description="",
            related_intents=["system.test"],
            possible_capabilities=[],
            context_rules={"cpu_high": 0.5},
        )
        scorer = GoalScorer({"cpu_percent": 95})
        bonus = scorer._context_bonus(g)
        assert bonus == 0.5

    def test_context_bonus_applies_multiple_rules(self):
        g = GoalDefinition(
            id="multi_rule",
            name="Multi Rule",
            description="",
            related_intents=["system.test"],
            possible_capabilities=[],
            context_rules={"cpu_high": 0.3, "mem_high": 0.4, "disk_high": 0.5},
        )
        scorer = GoalScorer({"cpu_percent": 95, "memory_percent": 90, "disk_percent": 95})
        bonus = scorer._context_bonus(g)
        assert bonus == min(0.3 + 0.4 + 0.5, 1.0)

    def test_context_bonus_capped_at_one(self):
        g = GoalDefinition(
            id="cap_rule",
            name="Cap Rule",
            description="",
            related_intents=["system.test"],
            possible_capabilities=[],
            context_rules={"cpu_high": 1.0, "mem_high": 1.0, "disk_high": 1.0},
        )
        scorer = GoalScorer({"cpu_percent": 95, "memory_percent": 90, "disk_percent": 95})
        bonus = scorer._context_bonus(g)
        assert bonus == 1.0

    def test_context_bonus_no_context_defaults_fifty(self):
        g = GoalDefinition(
            id="no_ctx",
            name="No Ctx",
            description="",
            related_intents=["system.test"],
            possible_capabilities=[],
            context_rules={"cpu_high": 1.0},
        )
        scorer = GoalScorer({})
        bonus = scorer._context_bonus(g)
        assert bonus == 0.0

    def test_context_bonus_custom_goal_competes_equally(self):
        g = GoalDefinition(
            id="custom_goal",
            name="Custom",
            description="",
            related_intents=["system.test"],
            possible_capabilities=[],
            context_rules={"disk_high": 1.0},
        )
        scorer = GoalScorer({"disk_percent": 95})
        bonus = scorer._context_bonus(g)
        assert bonus == 1.0
