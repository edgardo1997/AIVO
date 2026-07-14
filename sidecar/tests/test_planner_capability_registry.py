import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from sentinel.core.planner import Planner
from sentinel.core.intent import Intent
from sentinel.core.capability_registry import Capability, CapabilityRegistry, RiskLevel, capability_from_spec


def make_cap(cap_id: str, risk: RiskLevel = RiskLevel.LOW, description: str = "") -> Capability:
    return Capability(
        id=cap_id,
        name=cap_id,
        description=description,
        category="test",
        risk_level=risk,
        requires_confirmation=risk in (RiskLevel.HIGH, RiskLevel.CRITICAL),
        permissions=[],
        parameters={},
        result_type="json",
        tags=[],
        version="0.1.0",
        timeout_seconds=30,
    )


class TestPlannerRegistryPriority:
    def test_registry_takes_priority(self):
        registry = CapabilityRegistry()
        registry.register(make_cap("system.cpu"))
        planner = Planner(capability_registry=registry)
        plan = planner.plan(Intent(action="query", target="system.cpu"))
        assert len(plan.steps) == 1
        assert plan.steps[0].tool_id == "system.cpu"

    def test_fallback_to_step_definitions(self):
        registry = CapabilityRegistry()
        planner = Planner(capability_registry=registry)
        intent = Intent(action="query", target="system.memory")
        plan = planner.plan(intent)
        assert len(plan.steps) == 1
        assert plan.steps[0].tool_id == "system.info"

    def test_fallback_to_default(self):
        registry = CapabilityRegistry()
        planner = Planner(capability_registry=registry)
        plan = planner.plan(Intent(action="query", target="unknown.target"))
        assert len(plan.steps) == 1
        assert plan.steps[0].tool_id == "system.info"
        assert "unknown.target" in plan.steps[0].description

    def test_registry_unknown_falls_to_both(self):
        registry = CapabilityRegistry()
        cap = make_cap("some.tool")
        registry.register(cap)
        planner = Planner(capability_registry=registry)
        plan = planner.plan(Intent(action="query", target="unknown.other"))
        assert len(plan.steps) == 1
        assert plan.steps[0].tool_id == "system.info"


class TestRegistryRiskMapping:
    def test_low_risk_maps_to_low_impact(self):
        registry = CapabilityRegistry()
        registry.register(make_cap("test.tool", RiskLevel.LOW))
        plan = Planner(capability_registry=registry).plan(
            Intent(action="query", target="test.tool"))
        assert plan.steps[0].estimated_impact == "low"

    def test_medium_risk_maps_to_medium_impact(self):
        registry = CapabilityRegistry()
        registry.register(make_cap("test.tool", RiskLevel.MEDIUM))
        plan = Planner(capability_registry=registry).plan(
            Intent(action="query", target="test.tool"))
        assert plan.steps[0].estimated_impact == "medium"

    def test_high_risk_maps_to_high_impact(self):
        registry = CapabilityRegistry()
        registry.register(make_cap("test.tool", RiskLevel.HIGH))
        plan = Planner(capability_registry=registry).plan(
            Intent(action="query", target="test.tool"))
        assert plan.steps[0].estimated_impact == "high"

    def test_critical_risk_maps_to_critical_impact(self):
        registry = CapabilityRegistry()
        registry.register(make_cap("test.tool", RiskLevel.CRITICAL))
        plan = Planner(capability_registry=registry).plan(
            Intent(action="query", target="test.tool"))
        assert plan.steps[0].estimated_impact == "critical"


class TestRegistryReversible:
    def test_low_is_reversible(self):
        registry = CapabilityRegistry()
        registry.register(make_cap("test.tool", RiskLevel.LOW))
        plan = Planner(capability_registry=registry).plan(
            Intent(action="query", target="test.tool"))
        assert plan.steps[0].is_reversible is True

    def test_medium_is_reversible(self):
        registry = CapabilityRegistry()
        registry.register(make_cap("test.tool", RiskLevel.MEDIUM))
        plan = Planner(capability_registry=registry).plan(
            Intent(action="query", target="test.tool"))
        assert plan.steps[0].is_reversible is True

    def test_high_is_not_reversible(self):
        registry = CapabilityRegistry()
        registry.register(make_cap("test.tool", RiskLevel.HIGH))
        plan = Planner(capability_registry=registry).plan(
            Intent(action="query", target="test.tool"))
        assert plan.steps[0].is_reversible is False

    def test_critical_is_not_reversible(self):
        registry = CapabilityRegistry()
        registry.register(make_cap("test.tool", RiskLevel.CRITICAL))
        plan = Planner(capability_registry=registry).plan(
            Intent(action="query", target="test.tool"))
        assert plan.steps[0].is_reversible is False


class TestRegistryStepId:
    def test_step_id_from_capability(self):
        registry = CapabilityRegistry()
        registry.register(make_cap("system.cpu"))
        plan = Planner(capability_registry=registry).plan(
            Intent(action="query", target="system.cpu"))
        assert plan.steps[0].id == "cpu"

    def test_step_id_dotted(self):
        registry = CapabilityRegistry()
        registry.register(make_cap("executor.command"))
        plan = Planner(capability_registry=registry).plan(
            Intent(action="execute", target="executor.command"))
        assert plan.steps[0].id == "command"


class TestMultiStepUnaffected:
    def test_system_health_still_multistep(self):
        registry = CapabilityRegistry()
        registry.register(make_cap("system.cpu"))
        registry.register(make_cap("system.info"))
        registry.register(make_cap("system.processes"))
        planner = Planner(capability_registry=registry)
        intent = Intent(action="query", target="system.health")
        plan = planner.plan(intent)
        assert len(plan.steps) >= 2
        tool_ids = [s.tool_id for s in plan.steps]
        assert "system.cpu" in tool_ids
        assert "system.info" in tool_ids
        assert "system.processes" in tool_ids


class TestBackwardCompatNoRegistry:
    def test_planner_without_registry_unchanged(self):
        planner = Planner()
        intent = Intent(action="query", target="system.cpu")
        plan = planner.plan(intent)
        assert len(plan.steps) == 1
        assert plan.steps[0].tool_id == "system.cpu"
        assert plan.steps[0].id == "cpu"
        assert plan.steps[0].estimated_impact == "low"

    def test_without_registry_executor_has_medium_impact(self):
        planner = Planner()
        intent = Intent(action="execute", target="executor.command")
        plan = planner.plan(intent)
        assert plan.steps[0].estimated_impact == "medium"
        assert plan.steps[0].is_reversible is False

    def test_without_registry_system_health_multistep(self):
        planner = Planner()
        intent = Intent(action="query", target="system.health")
        plan = planner.plan(intent)
        assert len(plan.steps) == 4

    def test_empty_registry_same_as_no_registry(self):
        registry = CapabilityRegistry()
        planner = Planner(capability_registry=registry)
        intent = Intent(action="query", target="system.cpu")
        plan = planner.plan(intent)
        assert len(plan.steps) == 1
        assert plan.steps[0].tool_id == "system.cpu"


class TestCustomStepDefinitions:
    def test_custom_step_definitions_still_works(self):
        from sentinel.core.planner import PlanStep
        custom_defs = {
            "custom.target": [
                PlanStep(id="step1", tool_id="custom.tool", description="Custom step"),
            ],
        }
        planner = Planner(step_definitions=custom_defs)
        plan = planner.plan(Intent(action="query", target="custom.target"))
        assert len(plan.steps) == 1
        assert plan.steps[0].tool_id == "custom.tool"

    def test_custom_defs_with_registry_fallback(self):
        from sentinel.core.planner import PlanStep
        registry = CapabilityRegistry()
        custom_defs = {
            "custom.target": [
                PlanStep(id="step1", tool_id="custom.tool", description="Custom step"),
            ],
        }
        planner = Planner(step_definitions=custom_defs, capability_registry=registry)
        plan = planner.plan(Intent(action="query", target="custom.target"))
        assert len(plan.steps) == 1
        assert plan.steps[0].tool_id == "custom.tool"

    def test_registry_overrides_custom_defs(self):
        from sentinel.core.planner import PlanStep
        registry = CapabilityRegistry()
        registry.register(make_cap("override.tool"))
        custom_defs = {
            "override.tool": [
                PlanStep(id="old", tool_id="old.tool", description="Old step"),
            ],
        }
        planner = Planner(step_definitions=custom_defs, capability_registry=registry)
        plan = planner.plan(Intent(action="query", target="override.tool"))
        assert plan.steps[0].tool_id == "override.tool"
        assert plan.steps[0].id == "tool"


class TestPlannerUsesNewCapabilityFields:
    def test_planner_uses_explicit_estimated_impact(self):
        registry = CapabilityRegistry()
        cap = Capability(
            id="test.tool", name="Test", description="",
            category="test", risk_level=RiskLevel.LOW,
            requires_confirmation=False, permissions=[], parameters={},
            result_type="json", tags=[], version="0.1.0",
            timeout_seconds=10, estimated_impact="critical",
        )
        registry.register(cap)
        plan = Planner(capability_registry=registry).plan(
            Intent(action="query", target="test.tool"))
        assert plan.steps[0].estimated_impact == "critical"

    def test_planner_uses_explicit_reversible_true(self):
        registry = CapabilityRegistry()
        cap = Capability(
            id="test.tool", name="Test", description="",
            category="test", risk_level=RiskLevel.HIGH,
            requires_confirmation=True, permissions=[], parameters={},
            result_type="json", tags=[], version="0.1.0",
            timeout_seconds=10, reversible=True,
        )
        registry.register(cap)
        plan = Planner(capability_registry=registry).plan(
            Intent(action="execute", target="test.tool"))
        assert plan.steps[0].is_reversible is True

    def test_planner_uses_explicit_reversible_false(self):
        registry = CapabilityRegistry()
        cap = Capability(
            id="test.tool", name="Test", description="",
            category="test", risk_level=RiskLevel.LOW,
            requires_confirmation=False, permissions=[], parameters={},
            result_type="json", tags=[], version="0.1.0",
            timeout_seconds=10, reversible=False,
        )
        registry.register(cap)
        plan = Planner(capability_registry=registry).plan(
            Intent(action="query", target="test.tool"))
        assert plan.steps[0].is_reversible is False

    def test_planner_uses_default_parameters(self):
        registry = CapabilityRegistry()
        cap = Capability(
            id="test.tool", name="Test", description="",
            category="test", risk_level=RiskLevel.LOW,
            requires_confirmation=False, permissions=[], parameters={},
            result_type="json", tags=[], version="0.1.0",
            timeout_seconds=10, default_parameters={"limit": 25},
        )
        registry.register(cap)
        plan = Planner(capability_registry=registry).plan(
            Intent(action="query", target="test.tool"))
        assert plan.steps[0].params == {"limit": 25}

    def test_planner_fallback_estimated_impact_from_risk(self):
        registry = CapabilityRegistry()
        cap = Capability(
            id="test.tool", name="Test", description="",
            category="test", risk_level=RiskLevel.HIGH,
            requires_confirmation=True, permissions=[], parameters={},
            result_type="json", tags=[], version="0.1.0",
            timeout_seconds=10,
        )
        registry.register(cap)
        plan = Planner(capability_registry=registry).plan(
            Intent(action="execute", target="test.tool"))
        assert plan.steps[0].estimated_impact == "high"

    def test_planner_fallback_reversible_from_risk(self):
        registry = CapabilityRegistry()
        cap = Capability(
            id="test.tool", name="Test", description="",
            category="test", risk_level=RiskLevel.LOW,
            requires_confirmation=False, permissions=[], parameters={},
            result_type="json", tags=[], version="0.1.0",
            timeout_seconds=10,
        )
        registry.register(cap)
        plan = Planner(capability_registry=registry).plan(
            Intent(action="query", target="test.tool"))
        assert plan.steps[0].is_reversible is True

    def test_planner_fallback_reversible_false_for_high_risk(self):
        registry = CapabilityRegistry()
        cap = Capability(
            id="test.tool", name="Test", description="",
            category="test", risk_level=RiskLevel.HIGH,
            requires_confirmation=True, permissions=[], parameters={},
            result_type="json", tags=[], version="0.1.0",
            timeout_seconds=10,
        )
        registry.register(cap)
        plan = Planner(capability_registry=registry).plan(
            Intent(action="execute", target="test.tool"))
        assert plan.steps[0].is_reversible is False

    def test_planner_default_params_empty_when_not_set(self):
        registry = CapabilityRegistry()
        cap = Capability(
            id="test.tool", name="Test", description="",
            category="test", risk_level=RiskLevel.LOW,
            requires_confirmation=False, permissions=[], parameters={},
            result_type="json", tags=[], version="0.1.0",
            timeout_seconds=10,
        )
        registry.register(cap)
        plan = Planner(capability_registry=registry).plan(
            Intent(action="query", target="test.tool"))
        assert plan.steps[0].params == {}

    def test_planner_with_spec_sets_resolved_fields(self):
        registry = CapabilityRegistry()
        cap = capability_from_spec(
            spec_id="executor.command", name="Exec", description="Run command",
            version="0.1.0", parameters={}, permissions=["executor.command"],
            timeout_seconds=60, category="executor",
        )
        registry.register(cap)
        plan = Planner(capability_registry=registry).plan(
            Intent(action="execute", target="executor.command"))
        assert plan.steps[0].estimated_impact == "high"
        assert plan.steps[0].is_reversible is False
        assert plan.steps[0].params == {}


class TestPlannerPermissionMetadata:
    def test_capability_permission_level_available(self):
        registry = CapabilityRegistry()
        cap = capability_from_spec(
            spec_id="filesystem.write", name="Write", description="Write file",
            version="0.1.0", parameters={}, permissions=["filesystem.write"],
            timeout_seconds=30, category="filesystem",
            required_permission_level="admin",
        )
        registry.register(cap)
        retrieved = registry.get("filesystem.write")
        assert retrieved.required_permission_level == "admin"

    def test_capability_permission_level_default_none(self):
        registry = CapabilityRegistry()
        cap = capability_from_spec(
            spec_id="system.cpu", name="CPU", description="CPU info",
            version="0.1.0", parameters={}, permissions=["system.read"],
            timeout_seconds=10, category="system",
        )
        registry.register(cap)
        retrieved = registry.get("system.cpu")
        assert retrieved.required_permission_level is None
