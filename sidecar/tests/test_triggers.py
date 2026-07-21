import os
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import time
import pytest
from fastapi.testclient import TestClient
from main import app
from modules.permissions import _svc as perm_svc

from modules import triggers as triggers_mod
from sentinel.core.trigger import (
    TriggerRule,
    TriggerCondition,
    TriggerAction,
    TriggerOperator,
    TriggerEngine,
    TriggerFireRecord,
)

client = TestClient(app)


def setup_module():
    """Ensure trigger module is wired for testing."""
    # The test conftest already initializes the app; triggers_mod should be
    # already wired by main.py. We just ensure the engine is clean for tests.
    triggers_mod.get_engine()
    # Don't clear between tests - let the wrapper persist to DB. Instead,
    # individual tests use unique trigger IDs.


class TestTriggerCore:
    def test_create_rule(self):
        engine = TriggerEngine()
        rule = TriggerRule(
            id="test-rule",
            name="Test Rule",
            conditions=[TriggerCondition(metric="cpu_percent", operator=TriggerOperator.GT, value=90)],
            action=TriggerAction(tool_id="system.diagnostic", params={}),
            cooldown_seconds=60,
        )
        engine.add_rule(rule)
        assert engine.count() == 1
        assert engine.get_rule("test-rule") is rule

    def test_remove_rule(self):
        engine = TriggerEngine()
        engine.add_rule(TriggerRule(id="remove-me", name="Remove Me", conditions=[]))
        engine.remove_rule("remove-me")
        assert engine.count() == 0

    def test_remove_unknown_raises(self):
        engine = TriggerEngine()
        with pytest.raises(KeyError):
            engine.remove_rule("nonexistent")

    def test_condition_gt(self):
        cond = TriggerCondition(metric="cpu", operator=TriggerOperator.GT, value=90)
        assert cond.evaluate(95) is True
        assert cond.evaluate(89) is False
        assert cond.evaluate(90) is False

    def test_condition_lt(self):
        cond = TriggerCondition(metric="mem", operator=TriggerOperator.LT, value=50)
        assert cond.evaluate(30) is True
        assert cond.evaluate(60) is False

    def test_condition_gte(self):
        cond = TriggerCondition(metric="x", operator=TriggerOperator.GTE, value=10)
        assert cond.evaluate(10) is True
        assert cond.evaluate(11) is True
        assert cond.evaluate(9) is False

    def test_condition_lte(self):
        cond = TriggerCondition(metric="x", operator=TriggerOperator.LTE, value=10)
        assert cond.evaluate(10) is True
        assert cond.evaluate(9) is True
        assert cond.evaluate(11) is False

    def test_condition_eq(self):
        cond = TriggerCondition(metric="x", operator=TriggerOperator.EQ, value=42)
        assert cond.evaluate(42) is True
        assert cond.evaluate(41) is False

    def test_condition_neq(self):
        cond = TriggerCondition(metric="x", operator=TriggerOperator.NEQ, value=42)
        assert cond.evaluate(41) is True
        assert cond.evaluate(42) is False

    def test_can_fire_cooldown(self):
        rule = TriggerRule(id="cooldown", name="Cooldown", conditions=[], cooldown_seconds=100)
        assert rule.can_fire(0) is True
        rule.last_fired = 0
        assert rule.can_fire(50) is False
        assert rule.can_fire(100) is True
        assert rule.can_fire(150) is True

    def test_can_fire_disabled(self):
        rule = TriggerRule(id="disabled", name="Disabled", conditions=[], enabled=False)
        assert rule.can_fire() is False

    def test_evaluate_metrics_matches(self):
        engine = TriggerEngine()
        engine.add_rule(
            TriggerRule(
                id="high-cpu",
                name="High CPU",
                conditions=[TriggerCondition(metric="cpu_percent", operator=TriggerOperator.GT, value=80)],
                action=TriggerAction(tool_id="system.diagnostic"),
                cooldown_seconds=1,
            )
        )
        fires = engine.evaluate({"cpu_percent": 95})
        assert len(fires) == 1
        assert fires[0].trigger_id == "high-cpu"
        assert fires[0].condition_met is True

    def test_evaluate_no_metric_skips(self):
        engine = TriggerEngine()
        engine.add_rule(
            TriggerRule(
                id="skip",
                name="Skip",
                conditions=[TriggerCondition(metric="missing_metric", operator=TriggerOperator.GT, value=50)],
                cooldown_seconds=1,
            )
        )
        fires = engine.evaluate({"cpu_percent": 90})
        assert len(fires) == 0

    def test_evaluate_multiple_conditions(self):
        engine = TriggerEngine()
        engine.add_rule(
            TriggerRule(
                id="multi",
                name="Multi",
                conditions=[
                    TriggerCondition(metric="cpu", operator=TriggerOperator.GT, value=80),
                    TriggerCondition(metric="mem", operator=TriggerOperator.GT, value=90),
                ],
                cooldown_seconds=1,
            )
        )
        fires = engine.evaluate({"cpu": 85, "mem": 95})
        assert len(fires) == 1
        fires2 = engine.evaluate({"cpu": 85, "mem": 50})
        assert len(fires2) == 0

    def test_history_maintained(self):
        engine = TriggerEngine()
        engine.add_rule(
            TriggerRule(
                id="hist-test",
                name="History Test",
                conditions=[TriggerCondition(metric="x", operator=TriggerOperator.GT, value=50)],
                cooldown_seconds=1,
            )
        )
        engine.evaluate({"x": 90})
        assert len(engine.get_history()) == 1
        record = engine.get_history()[0]
        assert record.trigger_id == "hist-test"

    def test_roundtrip_dict(self):
        rule = TriggerRule(
            id="rt",
            name="Roundtrip",
            conditions=[TriggerCondition(metric="cpu", operator=TriggerOperator.GT, value=90)],
            action=TriggerAction(tool_id="diagnostic", params={"level": "full"}),
            cooldown_seconds=300,
        )
        d = rule.to_dict()
        restored = TriggerRule.from_dict(d)
        assert restored.id == "rt"
        assert restored.conditions[0].metric == "cpu"
        assert restored.conditions[0].operator == TriggerOperator.GT
        assert restored.action.tool_id == "diagnostic"
        assert restored.action.params == {"level": "full"}

    def test_update_rule(self):
        engine = TriggerEngine()
        engine.add_rule(TriggerRule(id="upd", name="Original", conditions=[], cooldown_seconds=300))
        engine.update_rule("upd", name="Updated", cooldown_seconds=600)
        rule = engine.get_rule("upd")
        assert rule.name == "Updated"
        assert rule.cooldown_seconds == 600

    def test_update_unknown_raises(self):
        engine = TriggerEngine()
        with pytest.raises(KeyError):
            engine.update_rule("nonexistent", name="X")

    def test_clear_history(self):
        engine = TriggerEngine()
        engine.add_rule(TriggerRule(id="clr", name="Clear", conditions=[], cooldown_seconds=1))
        engine.evaluate({"x": 100})
        engine.clear_history()
        assert len(engine.get_history()) == 0

    def test_action_execution(self):
        results = []

        async def mock_execute(tool_id, params):
            results.append((tool_id, params))

        engine = TriggerEngine(execute_fn=mock_execute)
        engine.add_rule(
            TriggerRule(
                id="action-test",
                name="Action Test",
                conditions=[TriggerCondition(metric="cpu", operator=TriggerOperator.GT, value=50)],
                action=TriggerAction(tool_id="test.tool", params={"key": "val"}),
                cooldown_seconds=1,
            )
        )
        engine.evaluate({"cpu": 90})
        # Action isn't awaited in evaluate since it uses create_task; check record
        history = engine.get_history()
        assert len(history) == 1
        assert results == [("test.tool", {"key": "val"})]
        assert history[0].action_executed is True

    def test_list_rules(self):
        engine = TriggerEngine()
        assert len(engine.list_rules()) == 0
        engine.add_rule(TriggerRule(id="a", name="A", conditions=[]))
        assert len(engine.list_rules()) == 1

    def test_concurrent_evaluation_respects_cooldown_once(self):
        engine = TriggerEngine()
        engine.add_rule(
            TriggerRule(
                id="concurrent",
                name="Concurrent",
                conditions=[TriggerCondition(metric="cpu", operator=TriggerOperator.GT, value=80)],
                cooldown_seconds=60,
            )
        )

        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(lambda _: engine.evaluate({"cpu": 95}), range(24)))

        assert sum(len(result) for result in results) == 1
        assert len(engine.get_history()) == 1

    def test_concurrent_duplicate_creation_accepts_only_one_rule(self):
        engine = TriggerEngine()

        def create(index):
            return engine.add_rule(
                TriggerRule(id="same-id", name=f"Rule {index}", conditions=[]),
                overwrite=False,
            )

        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(create, range(24)))

        assert results.count(True) == 1
        assert engine.count() == 1


class TestTriggerTools:
    def setup_method(self):
        perm_svc.set_level("admin")

    def test_trigger_list_empty(self):
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "trigger.list",
                "params": {},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "triggers" in data["data"]

    def test_trigger_create_and_list(self):
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "trigger.create",
                "params": {
                    "id": "test-trigger-tool",
                    "name": "Test Trigger",
                    "conditions": [{"metric": "cpu_percent", "operator": "gt", "value": 90}],
                    "action": {"tool_id": "system.diagnostic", "params": {}},
                    "cooldown_seconds": 60,
                },
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["status"] == "created"

        listed = client.post(
            "/v1/execute",
            json={
                "tool_id": "trigger.list",
                "params": {},
            },
        )
        assert listed.status_code == 200
        triggers = listed.json()["data"]["triggers"]
        ids = [t["id"] for t in triggers]
        assert "test-trigger-tool" in ids

    def test_trigger_create_duplicate_returns_error(self):
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "trigger.create",
                "params": {
                    "id": "dup-trigger",
                    "conditions": [{"metric": "cpu", "operator": "gt", "value": 80}],
                },
            },
        )
        assert resp.status_code == 200
        # Second create should fail
        resp2 = client.post(
            "/v1/execute",
            json={
                "tool_id": "trigger.create",
                "params": {
                    "id": "dup-trigger",
                    "conditions": [{"metric": "cpu", "operator": "gt", "value": 80}],
                },
            },
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["success"] is False

    def test_trigger_delete(self):
        client.post(
            "/v1/execute",
            json={
                "tool_id": "trigger.create",
                "params": {
                    "id": "del-trigger-tool",
                    "conditions": [{"metric": "cpu", "operator": "gt", "value": 90}],
                },
            },
        )
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "trigger.delete",
                "params": {"id": "del-trigger-tool"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["status"] == "deleted"

    def test_trigger_history_empty(self):
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "trigger.history",
                "params": {},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "history" in data["data"]

    def test_trigger_evaluate(self):
        client.post(
            "/v1/execute",
            json={
                "tool_id": "trigger.create",
                "params": {
                    "id": "eval-trigger",
                    "conditions": [{"metric": "cpu_percent", "operator": "gt", "value": 50}],
                    "cooldown_seconds": 1,
                },
            },
        )
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "trigger.evaluate",
                "params": {"metrics": {"cpu_percent": 90}},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["total_fired"] >= 1

    def test_trigger_tools_in_capabilities(self):
        resp = client.get("/api/sentinel/capabilities")
        data = resp.json()
        tool_ids = [t["id"] for t in data["tools"]]
        assert "trigger.list" in tool_ids
        assert "trigger.create" in tool_ids
        assert "trigger.delete" in tool_ids
        assert "trigger.history" in tool_ids
        assert "trigger.evaluate" in tool_ids

    def test_trigger_create_missing_id_returns_error(self):
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "trigger.create",
                "params": {"conditions": [{"metric": "cpu", "operator": "gt", "value": 80}]},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False

    def test_trigger_delete_unknown_returns_error(self):
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "trigger.delete",
                "params": {"id": "does-not-exist"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False

    def test_trigger_evaluate_no_metrics_returns_error(self):
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "trigger.evaluate",
                "params": {},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False


class TestTriggersAPI:
    def test_list_via_api(self):
        resp = client.get("/v1/triggers")
        assert resp.status_code == 200
        data = resp.json()
        assert "triggers" in data
        assert "total" in data

    def test_create_via_api(self):
        resp = client.post(
            "/v1/triggers",
            json={
                "id": "api-created-trigger",
                "name": "API Created",
                "description": "Created via REST API",
                "conditions": [{"metric": "memory_percent", "operator": "gt", "value": 95}],
                "action": {"tool_id": "system.diagnostic", "params": {"level": "memory"}},
                "cooldown_seconds": 120,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "created"
        assert data["trigger_id"] == "api-created-trigger"

        fetched = client.get("/v1/triggers/api-created-trigger")
        assert fetched.status_code == 200
        trigger = fetched.json()["trigger"]
        assert trigger["name"] == "API Created"
        assert trigger["conditions"][0]["metric"] == "memory_percent"

    def test_create_duplicate_via_api_returns_409(self):
        client.post(
            "/v1/triggers",
            json={
                "id": "dup-api-trigger",
                "conditions": [{"metric": "cpu", "operator": "gt", "value": 80}],
            },
        )
        resp = client.post(
            "/v1/triggers",
            json={
                "id": "dup-api-trigger",
                "conditions": [{"metric": "cpu", "operator": "gt", "value": 80}],
            },
        )
        assert resp.status_code == 409

    def test_update_via_api(self):
        client.post(
            "/v1/triggers",
            json={
                "id": "upd-api-trigger",
                "conditions": [{"metric": "cpu", "operator": "gt", "value": 80}],
            },
        )
        resp = client.patch(
            "/v1/triggers/upd-api-trigger",
            json={
                "name": "Updated Name",
                "cooldown_seconds": 600,
                "enabled": False,
            },
        )
        assert resp.status_code == 200
        fetched = client.get("/v1/triggers/upd-api-trigger")
        trigger = fetched.json()["trigger"]
        assert trigger["name"] == "Updated Name"
        assert trigger["cooldown_seconds"] == 600
        assert trigger["enabled"] is False

    def test_delete_via_api(self):
        client.post(
            "/v1/triggers",
            json={
                "id": "del-api-trigger",
                "conditions": [{"metric": "cpu", "operator": "gt", "value": 80}],
            },
        )
        resp = client.delete("/v1/triggers/del-api-trigger")
        assert resp.status_code == 200
        fetched = client.get("/v1/triggers/del-api-trigger")
        assert fetched.status_code == 404

    def test_get_unknown_returns_404(self):
        resp = client.get("/v1/triggers/does-not-exist")
        assert resp.status_code == 404

    def test_delete_unknown_returns_404(self):
        resp = client.delete("/v1/triggers/does-not-exist")
        assert resp.status_code == 404

    def test_history_via_api(self):
        client.post(
            "/v1/triggers",
            json={
                "id": "hist-api-trigger",
                "conditions": [{"metric": "disk_percent", "operator": "gt", "value": 95}],
                "cooldown_seconds": 1,
            },
        )
        resp = client.get("/v1/triggers/hist-api-trigger/history?limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert "history" in data

    def test_all_history_via_api(self):
        resp = client.get("/v1/triggers/history?limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert "history" in data
