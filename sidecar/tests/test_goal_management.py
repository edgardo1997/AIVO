import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from main import app

from sentinel.core.goals import (
    GoalRegistry, GoalDefinition, GoalAuditEntry, GoalScorerConfig,
    GoalScorer, GoalMatchResult, create_default_goal_registry,
)
from sentinel.core.capability_registry import RiskLevel

client = TestClient(app)


def make_goal(gid: str, intents: list = None, caps: list = None,
              priority: int = 0, risk: RiskLevel = RiskLevel.LOW,
              keywords: list = None) -> GoalDefinition:
    return GoalDefinition(
        id=gid,
        name=gid.replace("_", " ").title(),
        description=f"Goal {gid}",
        related_intents=intents or [],
        possible_capabilities=caps or [],
        priority=priority,
        base_risk=risk,
        keywords=keywords or [],
    )


class TestGoalRegistryDynamic:
    def test_unregister_removes_goal(self):
        registry = GoalRegistry()
        registry.register(make_goal("g1", intents=["system.test"]))
        assert registry.count() == 1
        registry.unregister("g1")
        assert registry.count() == 0
        assert registry.get("g1") is None

    def test_unregister_removes_from_index(self):
        registry = GoalRegistry()
        registry.register(make_goal("g1", intents=["system.test"]))
        registry.unregister("g1")
        assert registry.find_by_intent("system.test") == []

    def test_unregister_nonexistent_raises(self):
        registry = GoalRegistry()
        with pytest.raises(KeyError, match="not found"):
            registry.unregister("nonexistent")

    def test_update_partial_fields(self):
        registry = GoalRegistry()
        registry.register(make_goal("g1", intents=["system.test"], priority=1))
        registry.update("g1", {"priority": 5, "name": "Updated Goal"})
        goal = registry.get("g1")
        assert goal.priority == 5
        assert goal.name == "Updated Goal"

    def test_update_related_intents_rebuilds_index(self):
        registry = GoalRegistry()
        registry.register(make_goal("g1", intents=["system.a"]))
        registry.update("g1", {"related_intents": ["system.b"]})
        assert registry.find_by_intent("system.a") == []
        assert len(registry.find_by_intent("system.b")) == 1

    def test_update_nonexistent_raises(self):
        registry = GoalRegistry()
        with pytest.raises(KeyError, match="not found"):
            registry.update("nonexistent", {"priority": 5})

    def test_register_duplicate_raises(self):
        registry = GoalRegistry()
        registry.register(make_goal("g1"))
        with pytest.raises(ValueError, match="already registered"):
            registry.register(make_goal("g1"))


class TestGoalKeywords:
    def test_keywords_in_definition(self):
        g = make_goal("test", keywords=["monitor", "check"])
        assert g.keywords == ["monitor", "check"]

    def test_keywords_match_in_find_candidates(self):
        registry = GoalRegistry()
        registry.register(make_goal("mon", intents=["system.health"], keywords=["monitor"]))
        candidates = registry.find_candidates("monitor")
        assert len(candidates) >= 1
        assert candidates[0].goal.id == "mon"

    def test_keywords_empty_no_match(self):
        registry = GoalRegistry()
        registry.register(make_goal("g1", intents=["system.health"], keywords=[]))
        candidates = registry.find_candidates("monitor")
        assert candidates == []


class TestGoalAudit:
    def test_register_creates_audit_entry(self):
        registry = GoalRegistry()
        registry.register(make_goal("g1"), source="system")
        log = registry.get_audit_log()
        assert len(log) == 1
        assert log[0].operation == "REGISTER"
        assert log[0].goal_id == "g1"
        assert log[0].source == "system"

    def test_unregister_creates_audit_entry(self):
        registry = GoalRegistry()
        registry.register(make_goal("g1"))
        before = len(registry.get_audit_log())
        registry.unregister("g1", source="api")
        assert len(registry.get_audit_log()) == before + 1
        assert registry.get_audit_log()[-1].operation == "DELETE"
        assert registry.get_audit_log()[-1].source == "api"

    def test_update_creates_audit_entry(self):
        registry = GoalRegistry()
        registry.register(make_goal("g1"))
        before = len(registry.get_audit_log())
        registry.update("g1", {"priority": 5}, source="api")
        assert len(registry.get_audit_log()) == before + 1
        assert registry.get_audit_log()[-1].operation == "UPDATE"
        assert "changed_fields" in registry.get_audit_log()[-1].details

    def test_audit_entries_are_ordered(self):
        registry = GoalRegistry()
        registry.register(make_goal("a"))
        registry.register(make_goal("b"))
        registry.unregister("a")
        log = registry.get_audit_log()
        assert log[0].goal_id == "a"
        assert log[1].goal_id == "b"
        assert log[2].goal_id == "a"

    def test_audit_timestamps_are_iso(self):
        registry = GoalRegistry()
        registry.register(make_goal("g1"))
        ts = registry.get_audit_log()[0].timestamp
        assert "T" in ts
        assert ts.endswith("Z") or "+" in ts


class TestGoalScorerConfig:
    def test_default_config(self):
        cfg = GoalScorerConfig()
        assert cfg.min_confidence == 0.3
        assert cfg.confidence_weight == 0.6
        assert cfg.priority_weight == 0.2
        assert cfg.context_weight == 0.2

    def test_custom_weights(self):
        cfg = GoalScorerConfig(confidence_weight=0.5, priority_weight=0.3, context_weight=0.2)
        scorer = GoalScorer(config=cfg)
        registry = GoalRegistry()
        registry.register(make_goal("g1", intents=["test"], priority=5))
        candidates = registry.find_candidates("test")
        ranked = scorer.rank(candidates)
        if ranked:
            assert ranked[0].result.goal.id == "g1"

    def test_min_confidence_filters(self):
        cfg = GoalScorerConfig(min_confidence=0.9)
        scorer = GoalScorer(config=cfg)
        registry = GoalRegistry()
        registry.register(make_goal("g1", intents=["system.health"]))
        # exact match gives 1.0 confidence, should still pass
        candidates = registry.find_candidates("system.health")
        ranked = scorer.rank(candidates)
        assert len(ranked) == 1
        # fuzzy match would be below 0.9
        candidates2 = registry.find_candidates("health")
        ranked2 = scorer.rank(candidates2)
        assert len(ranked2) == 0

    def test_config_backward_compat(self):
        scorer = GoalScorer()
        assert scorer._config.min_confidence == 0.3


class TestGoalManagementApi:
    def setup_method(self):
        from modules.permissions import _svc as perm_svc
        perm_svc.set_level("admin")

    def test_post_goal_registers(self):
        resp = client.post("/api/sentinel/goals", json={
            "id": "custom_test",
            "name": "Custom Test",
            "intent_targets": ["system.custom"],
            "possible_capabilities": ["system.info"],
            "priority": 3,
        })
        assert resp.status_code == 201
        assert resp.json()["goal_id"] == "custom_test"

    def test_post_goal_duplicate(self):
        resp = client.post("/api/sentinel/goals", json={
            "id": "system_health_diagnosis",
            "intent_targets": ["system.health"],
            "possible_capabilities": ["system.info"],
        })
        assert resp.status_code == 409

    def test_post_goal_missing_id(self):
        resp = client.post("/api/sentinel/goals", json={
            "intent_targets": ["system.test"],
            "possible_capabilities": ["system.info"],
        })
        assert resp.status_code == 400

    def test_post_goal_empty_intents(self):
        resp = client.post("/api/sentinel/goals", json={
            "id": "bad_goal",
            "intent_targets": [],
            "possible_capabilities": ["system.info"],
        })
        assert resp.status_code == 400

    def test_post_goal_invalid_priority(self):
        resp = client.post("/api/sentinel/goals", json={
            "id": "bad_prio",
            "intent_targets": ["system.test"],
            "possible_capabilities": ["system.info"],
            "priority": 15,
        })
        assert resp.status_code == 400

    def test_post_goal_with_keywords(self):
        resp = client.post("/api/sentinel/goals", json={
            "id": "kw_goal",
            "intent_targets": ["system.test"],
            "possible_capabilities": ["system.info"],
            "keywords": ["monitor", "check"],
        })
        assert resp.status_code == 201
        from modules.sentinel_bridge import get_goal_registry
        goal = get_goal_registry().get("kw_goal")
        assert goal is not None
        assert "monitor" in goal.keywords

    def test_delete_goal(self):
        resp = client.post("/api/sentinel/goals", json={
            "id": "delete_me",
            "intent_targets": ["system.test"],
            "possible_capabilities": ["system.info"],
        })
        assert resp.status_code == 201
        resp = client.delete("/api/sentinel/goals/delete_me")
        assert resp.status_code == 200
        assert resp.json()["goal_id"] == "delete_me"

    def test_delete_nonexistent(self):
        resp = client.delete("/api/sentinel/goals/nope")
        assert resp.status_code == 404

    def test_patch_goal(self):
        resp = client.post("/api/sentinel/goals", json={
            "id": "patch_me",
            "intent_targets": ["system.test"],
            "possible_capabilities": ["system.info"],
            "priority": 1,
        })
        assert resp.status_code == 201
        resp = client.patch("/api/sentinel/goals/patch_me", json={
            "priority": 8,
            "name": "Patched Goal",
        })
        assert resp.status_code == 200
        from modules.sentinel_bridge import get_goal_registry
        goal = get_goal_registry().get("patch_me")
        assert goal.priority == 8
        assert goal.name == "Patched Goal"

    def test_patch_nonexistent(self):
        resp = client.patch("/api/sentinel/goals/nope", json={"priority": 5})
        assert resp.status_code == 404

    def test_patch_invalid_priority(self):
        resp = client.post("/api/sentinel/goals", json={
            "id": "bad_patch",
            "intent_targets": ["system.test"],
            "possible_capabilities": ["system.info"],
        })
        assert resp.status_code == 201
        resp = client.patch("/api/sentinel/goals/bad_patch", json={"priority": 42})
        assert resp.status_code == 400


class TestGoalManagementVerbose:
    def setup_method(self):
        from modules.permissions import _svc as perm_svc
        perm_svc.set_level("admin")

    def test_verbose_returns_breakdown(self):
        resp = client.get("/api/sentinel/goals/matches",
                          params={"intent": "system.health", "verbose": True})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["matches"]) >= 1
        m = data["matches"][0]
        assert "breakdown" in m
        assert "confidence_score" in m["breakdown"]
        assert "priority_score" in m["breakdown"]
        assert "context_score" in m["breakdown"]

    def test_non_verbose_no_breakdown(self):
        resp = client.get("/api/sentinel/goals/matches",
                          params={"intent": "system.health"})
        data = resp.json()
        assert "breakdown" not in data["matches"][0]

    def test_audit_api_returns_log(self):
        resp = client.get("/api/sentinel/goals/audit")
        assert resp.status_code == 200
        data = resp.json()
        assert "audit_log" in data
        assert isinstance(data["audit_log"], list)

    def test_audit_log_contains_api_operations(self):
        resp = client.post("/api/sentinel/goals", json={
            "id": "audit_test_g",
            "intent_targets": ["system.test"],
            "possible_capabilities": ["system.info"],
        })
        assert resp.status_code == 201
        resp = client.get("/api/sentinel/goals/audit")
        entries = [e for e in resp.json()["audit_log"]
                   if e["goal_id"] == "audit_test_g" and e["source"] == "api"]
        assert len(entries) >= 1
        assert entries[0]["operation"] == "REGISTER"

    def test_delete_appears_in_audit(self):
        resp = client.post("/api/sentinel/goals", json={
            "id": "audit_del",
            "intent_targets": ["system.test"],
            "possible_capabilities": ["system.info"],
        })
        assert resp.status_code == 201
        client.delete("/api/sentinel/goals/audit_del")
        resp = client.get("/api/sentinel/goals/audit")
        dels = [e for e in resp.json()["audit_log"]
                if e["goal_id"] == "audit_del" and e["operation"] == "DELETE"]
        assert len(dels) == 1


class TestBackwardCompatNoRegression:
    def test_existing_goals_still_match(self):
        resp = client.get("/api/sentinel/goals/matches",
                          params={"intent": "system.health"})
        data = resp.json()
        assert len(data["matches"]) >= 1
        assert data["matches"][0]["goal"] == "system_health_diagnosis"

    def test_planner_still_works(self):
        from sentinel.core.planner import Planner
        from sentinel.core.intent import Intent
        registry = create_default_goal_registry()
        planner = Planner(goal_registry=registry)
        plan = planner.plan(Intent(action="query", target="system.health"))
        assert plan.goal is not None
        assert plan.goal.id == "system_health_diagnosis"

    def test_goals_endpoint_still_lists(self):
        resp = client.get("/api/sentinel/goals")
        assert resp.status_code == 200
        ids = [g["id"] for g in resp.json()["goals"]]
        assert "system_health_diagnosis" in ids

    def test_goal_scorer_defaults_not_broken(self):
        from sentinel.core.goals import GoalScorerConfig
        cfg = GoalScorerConfig()
        assert cfg.confidence_weight == 0.6
        assert cfg.priority_weight == 0.2
        assert cfg.context_weight == 0.2


class TestGoalAdminAuth:
    def test_require_admin_raises_when_not_admin(self):
        from modules.sentinel_bridge import _require_admin
        import unittest.mock as mock
        with mock.patch("modules.permissions._svc") as mock_svc:
            mock_svc.repo.load.return_value = {"level": "confirm"}
            with pytest.raises(HTTPException, match="Admin level required"):
                _require_admin()

    def test_require_admin_passes_when_admin(self):
        from modules.sentinel_bridge import _require_admin
        import unittest.mock as mock
        with mock.patch("modules.permissions._svc") as mock_svc:
            mock_svc.repo.load.return_value = {"level": "admin"}
            _require_admin()

    def test_require_admin_raises_on_view_level(self):
        from modules.sentinel_bridge import _require_admin
        import unittest.mock as mock
        with mock.patch("modules.permissions._svc") as mock_svc:
            mock_svc.repo.load.return_value = {"level": "view"}
            with pytest.raises(HTTPException, match="Admin level required"):
                _require_admin()


class TestGoalCapabilityValidation:
    def test_validate_valid_capabilities(self):
        from modules.sentinel_bridge import _validate_capabilities
        invalid = _validate_capabilities(["system.info", "system.cpu"])
        assert invalid == []

    def test_validate_unknown_capability(self):
        from modules.sentinel_bridge import _validate_capabilities
        invalid = _validate_capabilities(["nonexistent.cap"])
        assert "nonexistent.cap" in invalid

    def test_validate_mixed_known_and_unknown(self):
        from modules.sentinel_bridge import _validate_capabilities
        invalid = _validate_capabilities(["system.info", "bogus.cap", "system.cpu", "fake.tool"])
        assert "bogus.cap" in invalid
        assert "fake.tool" in invalid
        assert "system.info" not in invalid


class TestGoalDefinitionContextRulesBridge:
    def test_goal_to_dict_includes_context_rules(self):
        from sentinel.core.goals import GoalDefinition, RiskLevel
        g = GoalDefinition(
            id="ctx_api", name="Ctx API", description="",
            related_intents=["system.test"],
            possible_capabilities=["system.info"],
            context_rules={"cpu_high": 0.6},
        )
        d = g.to_dict()
        assert d["context_rules"] == {"cpu_high": 0.6}
        assert d["enabled"] is True

    def test_goal_to_dict_includes_timestamps(self):
        from sentinel.core.goals import GoalDefinition, RiskLevel
        g = GoalDefinition(
            id="ts_api", name="TS API", description="",
            related_intents=["system.test"],
            possible_capabilities=["system.info"],
        )
        d = g.to_dict()
        assert "created_at" in d
        assert "updated_at" in d

    def test_context_rules_in_get_goals_endpoint(self):
        resp = client.get("/api/sentinel/goals")
        assert resp.status_code == 200
        data = resp.json()
        for g in data["goals"]:
            assert "context_rules" in g
            assert "enabled" in g
            assert "created_at" in g
            assert "updated_at" in g
