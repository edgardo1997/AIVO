import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import threading
import pytest
from sentinel.core.goals import Goal, GoalDefinition, GoalRegistry
from sentinel.core.capability_registry import RiskLevel


def make_goal(gid: str, intents: list = None, caps: list = None,
              priority: int = 0, risk: RiskLevel = RiskLevel.LOW) -> GoalDefinition:
    return GoalDefinition(
        id=gid,
        name=gid.replace("_", " ").title(),
        description=f"Goal {gid}",
        related_intents=intents or [],
        possible_capabilities=caps or [],
        priority=priority,
        base_risk=risk,
    )


class TestGoalRegistration:
    def test_register_and_get(self):
        registry = GoalRegistry()
        goal = make_goal("improve_performance")
        registry.register(goal)
        retrieved = registry.get("improve_performance")
        assert retrieved is not None
        assert retrieved.id == "improve_performance"
        assert retrieved.name == "Improve Performance"

    def test_register_duplicate_raises(self):
        registry = GoalRegistry()
        registry.register(make_goal("test.goal"))
        with pytest.raises(ValueError, match="already registered"):
            registry.register(make_goal("test.goal"))

    def test_get_nonexistent(self):
        registry = GoalRegistry()
        assert registry.get("nonexistent") is None

    def test_list_all(self):
        registry = GoalRegistry()
        g1 = make_goal("g1")
        g2 = make_goal("g2")
        registry.register(g1)
        registry.register(g2)
        assert len(registry.list_all()) == 2

    def test_count(self):
        registry = GoalRegistry()
        assert registry.count() == 0
        registry.register(make_goal("g1"))
        assert registry.count() == 1

    def test_clear(self):
        registry = GoalRegistry()
        registry.register(make_goal("g1"))
        registry.clear()
        assert registry.count() == 0
        assert registry.get("g1") is None


class TestGoalFindByIntent:
    def test_find_by_intent_single(self):
        registry = GoalRegistry()
        goal = make_goal("diagnose", intents=["system.health", "system.cpu"])
        registry.register(goal)
        found = registry.find_by_intent("system.health")
        assert len(found) == 1
        assert found[0].id == "diagnose"

    def test_find_by_intent_multi(self):
        registry = GoalRegistry()
        g1 = make_goal("diagnose", intents=["system.health"])
        g2 = make_goal("monitor", intents=["system.health"])
        registry.register(g1)
        registry.register(g2)
        found = registry.find_by_intent("system.health")
        assert len(found) == 2

    def test_find_by_intent_no_match(self):
        registry = GoalRegistry()
        registry.register(make_goal("test", intents=["other"]))
        found = registry.find_by_intent("nonexistent")
        assert found == []

    def test_find_by_intent_empty_registry(self):
        registry = GoalRegistry()
        assert registry.find_by_intent("anything") == []


class TestGoalSerialization:
    def test_to_dict(self):
        goal = make_goal("improve_performance", intents=["system.health"],
                         caps=["system.cpu", "system.info"], risk=RiskLevel.MEDIUM)
        d = goal.to_dict()
        assert d["id"] == "improve_performance"
        assert d["base_risk"] == "medium"
        assert d["related_intents"] == ["system.health"]
        assert d["possible_capabilities"] == ["system.cpu", "system.info"]

    def test_from_dict(self):
        d = {
            "id": "diagnose",
            "name": "Diagnose",
            "description": "Diagnose system",
            "related_intents": ["system.health"],
            "possible_capabilities": ["system.cpu"],
            "priority": 5,
            "base_risk": "high",
        }
        goal = GoalDefinition.from_dict(d)
        assert goal.id == "diagnose"
        assert goal.base_risk == RiskLevel.HIGH
        assert goal.related_intents == ["system.health"]
        assert goal.priority == 5

    def test_roundtrip(self):
        goal = make_goal("cleanup", intents=["system.disk"],
                         caps=["filesystem.list", "filesystem.write"],
                         risk=RiskLevel.LOW, priority=3)
        d = goal.to_dict()
        restored = GoalDefinition.from_dict(d)
        assert restored.id == goal.id
        assert restored.base_risk == goal.base_risk
        assert restored.related_intents == goal.related_intents
        assert restored.possible_capabilities == goal.possible_capabilities
        assert restored.priority == goal.priority


class TestGoalObject:
    def test_goal_wraps_definition(self):
        gd = make_goal("test.goal", intents=["sys.health"], caps=["sys.cpu"])
        goal = Goal(definition=gd, context={"key": "val"})
        assert goal.id == "test.goal"
        assert goal.name == "Test.Goal"
        assert goal.base_risk == RiskLevel.LOW
        assert goal.related_intents == ["sys.health"]
        assert goal.possible_capabilities == ["sys.cpu"]
        assert goal.context == {"key": "val"}

    def test_goal_without_context(self):
        gd = make_goal("simple")
        goal = Goal(definition=gd)
        assert goal.context is None
        assert goal.priority == 0


class TestGoalThreadSafety:
    def test_concurrent_register(self):
        registry = GoalRegistry()
        errors = []

        def worker(ident):
            try:
                g = make_goal(f"goal.{ident}", intents=[f"intent.{ident}"],
                              caps=[f"cap.{ident}"])
                registry.register(g)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(errors) == 0
        assert registry.count() == 20

    def test_concurrent_read_write(self):
        registry = GoalRegistry()
        for i in range(10):
            registry.register(make_goal(f"pre.{i}", intents=["common"]))

        errors = []

        def writer(ident):
            try:
                g = make_goal(f"dyn.{ident}", intents=["common"])
                registry.register(g)
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                _ = registry.list_all()
                _ = registry.count()
                _ = registry.find_by_intent("common")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(10)]
        threads += [threading.Thread(target=reader) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(errors) == 0


class TestGoalPriority:
    def test_priority_ordering(self):
        registry = GoalRegistry()
        low = make_goal("low_priority", intents=["system.health"], priority=1)
        high = make_goal("high_priority", intents=["system.health"], priority=10)
        registry.register(low)
        registry.register(high)
        found = registry.find_by_intent("system.health")
        assert len(found) == 2
        best = max(found, key=lambda g: g.priority)
        assert best.id == "high_priority"

    def test_default_priority_zero(self):
        g = make_goal("test")
        assert g.priority == 0


class TestGoalDefinitionHardening:
    def test_new_fields_defaults(self):
        g = make_goal("harden_test", intents=["system.test"])
        assert g.enabled is True
        assert g.context_rules == {}
        assert g.created_at != ""
        assert g.updated_at != ""

    def test_context_rules_stored_and_returned(self):
        g = make_goal("ctx_goal", intents=["system.test"])
        g.context_rules = {"cpu_high": 0.5, "disk_high": 1.0}
        assert g.context_rules["cpu_high"] == 0.5
        assert g.context_rules["disk_high"] == 1.0

    def test_created_at_and_updated_at_set_on_creation(self):
        g = GoalDefinition(
            id="time_test",
            name="Time Test",
            description="",
            related_intents=["system.test"],
            possible_capabilities=[],
        )
        assert g.created_at != ""
        assert g.updated_at != ""
        assert g.created_at == g.updated_at

    def test_updated_at_changes_on_update(self):
        import time
        registry = GoalRegistry()
        g = make_goal("update_time", intents=["system.test"])
        registry.register(g)
        old_updated = g.updated_at
        time.sleep(0.01)
        registry.update("update_time", {"priority": 9})
        assert g.updated_at != old_updated

    def test_enabled_flag_respected(self):
        g = make_goal("disabled_g", intents=["system.test"])
        g.enabled = False
        assert g.enabled is False

    def test_context_rules_in_to_dict(self):
        g = GoalDefinition(
            id="dict_ctx",
            name="Dict Ctx",
            description="",
            related_intents=["system.test"],
            possible_capabilities=[],
            context_rules={"cpu_high": 0.7},
        )
        d = g.to_dict()
        assert d["context_rules"] == {"cpu_high": 0.7}
        assert d["enabled"] is True
        assert "created_at" in d
        assert "updated_at" in d

    def test_context_rules_roundtrip(self):
        g = GoalDefinition(
            id="roundtrip_ctx",
            name="Roundtrip Ctx",
            description="",
            related_intents=["system.test"],
            possible_capabilities=[],
            context_rules={"mem_high": 0.4, "disk_high": 0.8},
        )
        d = g.to_dict()
        restored = GoalDefinition.from_dict(d)
        assert restored.context_rules == {"mem_high": 0.4, "disk_high": 0.8}
        assert restored.enabled is True


class TestGoalRegistryUpdateValidation:
    def test_update_allows_valid_fields(self):
        registry = GoalRegistry()
        registry.register(make_goal("g1", intents=["system.test"], priority=1))
        registry.update("g1", {"priority": 5, "name": "Updated"})
        assert registry.get("g1").priority == 5
        assert registry.get("g1").name == "Updated"

    def test_update_rejects_disallowed_fields(self):
        registry = GoalRegistry()
        registry.register(make_goal("g1", intents=["system.test"]))
        with pytest.raises(ValueError, match="not allowed"):
            registry.update("g1", {"nonexistent_field": "val"})

    def test_update_allows_context_rules(self):
        registry = GoalRegistry()
        registry.register(make_goal("g1", intents=["system.test"]))
        registry.update("g1", {"context_rules": {"cpu_high": 0.9}})
        assert registry.get("g1").context_rules == {"cpu_high": 0.9}

    def test_update_allows_enabled(self):
        registry = GoalRegistry()
        registry.register(make_goal("g1", intents=["system.test"]))
        registry.update("g1", {"enabled": False})
        assert registry.get("g1").enabled is False


class TestGoalAuditDetailsDict:
    def test_register_details_is_dict(self):
        registry = GoalRegistry()
        registry.register(make_goal("g1", intents=["system.test"]))
        entry = registry.get_audit_log()[0]
        assert isinstance(entry.details, dict)
        assert "priority" in entry.details
        assert "intents" in entry.details

    def test_update_details_is_dict_with_field_list(self):
        registry = GoalRegistry()
        registry.register(make_goal("g1", intents=["system.test"]))
        registry.update("g1", {"priority": 7})
        update_entry = registry.get_audit_log()[-1]
        assert isinstance(update_entry.details, dict)
        assert "changed_fields" in update_entry.details
        assert "priority" in update_entry.details["changed_fields"]

    def test_delete_details_is_dict(self):
        registry = GoalRegistry()
        registry.register(make_goal("g1", intents=["system.test"]))
        registry.unregister("g1")
        delete_entry = registry.get_audit_log()[-1]
        assert isinstance(delete_entry.details, dict)
        assert "goal_id" in delete_entry.details


class TestGoalAuditEviction:
    def test_fifo_eviction_at_limit(self):
        registry = GoalRegistry(max_audit_entries=5)
        for i in range(10):
            registry.register(make_goal(f"g{i}", intents=[f"system.test{i}"]))
        log = registry.get_audit_log()
        assert len(log) == 5
        assert log[0].goal_id == "g5"
        assert log[-1].goal_id == "g9"

    def test_set_max_audit_entries_dynamically(self):
        registry = GoalRegistry(max_audit_entries=20)
        for i in range(10):
            registry.register(make_goal(f"g{i}", intents=[f"system.test{i}"]))
        assert len(registry.get_audit_log()) == 10
        registry.set_max_audit_entries(3)
        assert len(registry.get_audit_log()) == 3
        assert registry.get_audit_log()[0].goal_id == "g7"
