import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch
import pytest

from sentinel.core.plan_cache import PlanCache, _cache_key, _serialize_plan, _deserialize_plan
from sentinel.core.planner import Plan, PlanStep
from sentinel.core.intent import Intent
from sentinel.core.model_router import TaskType, RouterDecision


class TestPlanCacheKey:
    def test_same_intent_same_key(self):
        a = Intent(action="query", target="system.info", parameters={}, confidence=0.9, raw_input="info")
        b = Intent(action="query", target="system.info", parameters={}, confidence=0.5, raw_input="show info")
        assert _cache_key(a) == _cache_key(b)

    def test_different_action_different_key(self):
        a = Intent(action="query", target="system.info", parameters={}, confidence=0.9, raw_input="")
        b = Intent(action="execute", target="system.info", parameters={}, confidence=0.9, raw_input="")
        assert _cache_key(a) != _cache_key(b)

    def test_different_target_different_key(self):
        a = Intent(action="query", target="system.info", parameters={}, confidence=0.9, raw_input="")
        b = Intent(action="query", target="system.cpu", parameters={}, confidence=0.9, raw_input="")
        assert _cache_key(a) != _cache_key(b)

    def test_different_params_different_key(self):
        a = Intent(action="write", target="filesystem.write", parameters={"path": "/a"}, confidence=0.9, raw_input="")
        b = Intent(action="write", target="filesystem.write", parameters={"path": "/b"}, confidence=0.9, raw_input="")
        assert _cache_key(a) != _cache_key(b)

    def test_sorted_params_same_key(self):
        a = Intent(action="write", target="filesystem.write", parameters={"z": 1, "a": 2}, confidence=0.9, raw_input="")
        b = Intent(action="write", target="filesystem.write", parameters={"a": 2, "z": 1}, confidence=0.9, raw_input="")
        assert _cache_key(a) == _cache_key(b)


class TestPlanCache:
    def make_intent(self, action="query", target="system.info"):
        return Intent(action=action, target=target, parameters={}, confidence=0.9, raw_input=target)

    def make_plan(self, intent, tool_ids=("system.info",)):
        steps = [PlanStep(id=f"s{i}", tool_id=tid) for i, tid in enumerate(tool_ids)]
        return Plan(steps=steps, intent=intent, description="test plan")

    def test_set_and_get(self):
        cache = PlanCache()
        intent = self.make_intent()
        plan = self.make_plan(intent)
        cache.set(intent, plan)
        got = cache.get(intent)
        assert got is not None
        assert len(got.steps) == 1
        assert got.steps[0].tool_id == "system.info"

    def test_miss_returns_none(self):
        cache = PlanCache()
        intent = self.make_intent()
        got = cache.get(intent)
        assert got is None

    def test_hit_increments_count(self):
        cache = PlanCache()
        intent = self.make_intent()
        cache.set(intent, self.make_plan(intent))
        cache.get(intent)
        cache.get(intent)
        stats = cache.stats()
        assert stats["entries"][0]["hit_count"] == 2

    def test_max_entries_evicts_oldest(self):
        cache = PlanCache(max_entries=2)
        for i in range(3):
            intent = self.make_intent(target=f"system.tool{i}")
            cache.set(intent, self.make_plan(intent))
        stats = cache.stats()
        assert stats["size"] == 2

    def test_ttl_expiry(self):
        cache = PlanCache(default_ttl=0)
        intent = self.make_intent()
        cache.set(intent, self.make_plan(intent), ttl=0)
        got = cache.get(intent)
        assert got is None

    def test_invalidate(self):
        cache = PlanCache()
        intent = self.make_intent()
        cache.set(intent, self.make_plan(intent))
        assert cache.invalidate(intent) is True
        assert cache.get(intent) is None

    def test_invalidate_miss(self):
        cache = PlanCache()
        assert cache.invalidate(self.make_intent()) is False

    def test_clear(self):
        cache = PlanCache()
        for i in range(3):
            intent = self.make_intent(target=f"system.t{i}")
            cache.set(intent, self.make_plan(intent))
        assert cache.clear() == 3
        assert cache.stats()["size"] == 0

    def test_cache_key_ignores_confidence_and_raw_input(self):
        a = Intent(action="query", target="sys.info", parameters={"x": 1}, confidence=0.9, raw_input="a")
        b = Intent(action="query", target="sys.info", parameters={"x": 1}, confidence=0.3, raw_input="b")
        assert _cache_key(a) == _cache_key(b)

    def test_roundtrip_with_model_decision(self):
        cache = PlanCache()
        intent = self.make_intent()
        md = RouterDecision(
            provider_id="ollama", model="llama3",
            task_type=TaskType.QUICK, strategy="priority", reason="test",
        )
        step = PlanStep(id="s0", tool_id="system.info", model_decision=md)
        plan = Plan(steps=[step], intent=intent, description="with md")
        cache.set(intent, plan)
        got = cache.get(intent)
        assert got is not None
        assert got.steps[0].model_decision is not None
        assert got.steps[0].model_decision.provider_id == "ollama"


class TestPlanCacheAPI:
    def setup_method(self):
        from modules.sentinel_bridge import reset_bridge
        reset_bridge()

    def test_cache_stats(self):
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        resp = client.get("/api/sentinel/cache/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "enabled" in data

    def test_cache_clear(self):
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        resp = client.post("/api/sentinel/cache/clear")
        assert resp.status_code == 200
        data = resp.json()
        assert "cleared" in data
