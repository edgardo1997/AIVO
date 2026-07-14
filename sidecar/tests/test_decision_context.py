import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from conftest import TEST_IDENTITY
from sentinel.core.decision_engine import DecisionEngine, DecisionResult, Decision, _extract_context_factors
from sentinel.core.planner import Plan, PlanStep
from sentinel.core.intent import Intent


def _make_plan(steps=None, risk=0.3):
    return Plan(
        steps=steps or [PlanStep(id="s1", tool_id="system.info", description="test")],
        intent=Intent(action="query", target="system.info", raw_input="test"),
        risk_score=risk,
    )


class TestContextFactorsExtraction:
    def test_empty_context_returns_empty_factors(self):
        assert _extract_context_factors({}) == []

    def test_no_summary_returns_empty(self):
        assert _extract_context_factors({"system": {}}) == []

    def test_cpu_normal_no_factors(self):
        ctx = {"system_summary": {"cpu_percent": 30}}
        assert _extract_context_factors(ctx) == []

    def test_cpu_high_detected(self):
        ctx = {"system_summary": {"cpu_percent": 85}}
        factors = _extract_context_factors(ctx)
        assert "cpu_high" in factors

    def test_cpu_critical_detected(self):
        ctx = {"system_summary": {"cpu_percent": 95}}
        factors = _extract_context_factors(ctx)
        assert "cpu_critical" in factors

    def test_memory_high_detected(self):
        ctx = {"system_summary": {"memory_percent": 85}}
        factors = _extract_context_factors(ctx)
        assert "memory_high" in factors

    def test_memory_critical_detected(self):
        ctx = {"system_summary": {"memory_percent": 95}}
        factors = _extract_context_factors(ctx)
        assert "memory_critical" in factors

    def test_disk_high_detected(self):
        ctx = {"system_summary": {"disk_percent": 90}}
        factors = _extract_context_factors(ctx)
        assert "disk_high" in factors

    def test_disk_critical_detected(self):
        ctx = {"system_summary": {"disk_percent": 98}}
        factors = _extract_context_factors(ctx)
        assert "disk_critical" in factors

    def test_many_processes_detected(self):
        ctx = {"system_summary": {"process_count": 250}}
        factors = _extract_context_factors(ctx)
        assert "many_processes" in factors

    def test_multiple_factors_combined(self):
        ctx = {"system_summary": {"cpu_percent": 95, "memory_percent": 92, "disk_percent": 50, "process_count": 80}}
        factors = _extract_context_factors(ctx)
        assert "cpu_critical" in factors
        assert "memory_critical" in factors
        assert "disk_high" not in factors
        assert "many_processes" not in factors


class TestDecisionEngineWithContext:
    def test_evaluate_without_context_still_works(self):
        engine = DecisionEngine(get_permission_level=lambda: "admin")
        plan = _make_plan(risk=0.2)
        result = engine.evaluate(plan)
        assert result.decision == Decision.APPROVE

    def test_evaluate_with_empty_context(self):
        engine = DecisionEngine(get_permission_level=lambda: "admin")
        plan = _make_plan(risk=0.2)
        result = engine.evaluate(plan, {})
        assert result.decision == Decision.APPROVE
        assert result.context_factors == []

    def test_evaluate_with_context_returns_factors(self):
        engine = DecisionEngine(get_permission_level=lambda: "admin")
        plan = _make_plan(risk=0.2)
        ctx = {"system_summary": {"cpu_percent": 95, "memory_percent": 92}}
        result = engine.evaluate(plan, ctx)
        assert "cpu_critical" in result.context_factors
        assert "memory_critical" in result.context_factors

    def test_reject_decision_includes_context_factors(self):
        engine = DecisionEngine(get_permission_level=lambda: "view")
        plan = _make_plan(risk=0.8)
        ctx = {"system_summary": {"cpu_percent": 95}}
        result = engine.evaluate(plan, ctx)
        assert result.decision == Decision.REJECT
        assert "cpu_critical" in result.context_factors

    def test_require_confirm_includes_context_factors(self):
        engine = DecisionEngine(get_permission_level=lambda: "confirm")
        plan = _make_plan(risk=0.5)
        ctx = {"system_summary": {"memory_percent": 85}}
        result = engine.evaluate(plan, ctx)
        assert result.decision == Decision.REQUIRE_CONFIRM
        assert "memory_high" in result.context_factors

    def test_decision_result_is_serializable(self):
        result = DecisionResult(
            decision=Decision.APPROVE,
            plan=_make_plan(),
            reason="test",
            context_factors=["cpu_high", "memory_high"],
        )
        d = {"decision": result.decision, "factors": result.context_factors}
        assert d["decision"] == "approve"
        assert d["factors"] == ["cpu_high", "memory_high"]


class TestContextAwareRiskScoring:
    def test_risk_base_without_context(self):
        engine = DecisionEngine(get_permission_level=lambda: "confirm")
        plan = _make_plan(risk=0.3)
        result = engine.evaluate(plan)
        assert result.base_risk_score == 0.3
        assert result.context_modifier == 0.0
        assert result.final_risk_score == 0.3

    def test_risk_increased_with_cpu_critical(self):
        engine = DecisionEngine(get_permission_level=lambda: "confirm")
        plan = _make_plan(risk=0.3)
        ctx = {"system_summary": {"cpu_percent": 95}}
        result = engine.evaluate(plan, ctx)
        assert result.base_risk_score == 0.3
        assert result.context_modifier == 0.10
        assert result.final_risk_score == 0.40

    def test_risk_increased_with_memory_critical(self):
        engine = DecisionEngine(get_permission_level=lambda: "confirm")
        plan = _make_plan(risk=0.3)
        ctx = {"system_summary": {"memory_percent": 95}}
        result = engine.evaluate(plan, ctx)
        assert result.context_modifier == 0.15
        assert result.final_risk_score == pytest.approx(0.45)

    def test_risk_combined_factors(self):
        engine = DecisionEngine(get_permission_level=lambda: "confirm")
        plan = _make_plan(risk=0.3)
        ctx = {"system_summary": {"cpu_percent": 95, "memory_percent": 95, "disk_percent": 97, "process_count": 250}}
        result = engine.evaluate(plan, ctx)
        assert result.context_modifier == 0.40  # 0.10 + 0.15 + 0.10 + 0.05
        assert result.final_risk_score == 0.70

    def test_risk_caps_at_one(self):
        engine = DecisionEngine(get_permission_level=lambda: "confirm")
        plan = _make_plan(risk=0.9)
        ctx = {"system_summary": {"memory_percent": 95}}
        result = engine.evaluate(plan, ctx)
        assert result.final_risk_score == 1.0

    def test_context_modifier_can_push_auto_to_confirm(self):
        engine = DecisionEngine(get_permission_level=lambda: "confirm")
        plan = _make_plan(risk=0.3)
        ctx = {"system_summary": {"memory_percent": 95}}
        result = engine.evaluate(plan, ctx)
        assert result.base_risk_score == 0.3
        assert result.context_modifier == 0.15
        assert result.final_risk_score == pytest.approx(0.45)
        assert result.decision == Decision.REQUIRE_CONFIRM, \
            f"Context modifier pushed risk to require confirm, got {result.decision}"

    def test_context_modifier_pushes_to_reject(self):
        engine = DecisionEngine(get_permission_level=lambda: "view")
        plan = _make_plan(risk=0.10)
        ctx = {"system_summary": {"memory_percent": 95}}
        result = engine.evaluate(plan, ctx)
        assert result.final_risk_score == 0.25
        assert result.decision == Decision.REJECT, \
            "View level rejects at risk > 0.10, context pushed base 0.10 to 0.25 > 0.10"

    def test_no_modifier_unrelated_factors(self):
        engine = DecisionEngine(get_permission_level=lambda: "confirm")
        plan = _make_plan(risk=0.3)
        ctx = {"system_summary": {"cpu_percent": 60, "memory_percent": 50, "disk_percent": 40, "process_count": 80}}
        result = engine.evaluate(plan, ctx)
        assert result.context_modifier == 0.0
        assert result.final_risk_score == 0.3


class TestDecisionFlowIntegration:
    def test_skip_decision_still_works(self):
        engine = DecisionEngine()
        intent = Intent(action="query", target="system.cpu", confidence=0.8, raw_input="cpu")
        assert engine.should_skip_decision(intent) is True

    def test_dont_skip_execute_intent(self):
        engine = DecisionEngine()
        intent = Intent(action="execute", target="executor.command", confidence=0.8, raw_input="run command")
        assert engine.should_skip_decision(intent) is False

    def test_dont_skip_low_confidence_query(self):
        engine = DecisionEngine()
        intent = Intent(action="query", target="system.info", confidence=0.3, raw_input="hmm")
        assert engine.should_skip_decision(intent) is False

    def test_context_factors_in_sentinel_bridge_response(self):
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        resp = client.post("/api/sentinel/process", json={"utterance": "cpu usage"})
        assert resp.status_code == 200
        data = resp.json()
        assert "context_factors" in data, "Response must include context_factors"
        assert isinstance(data["context_factors"], list)

    def test_orchestrator_passes_context_to_decision(self):
        from modules import get_gateway, init_sentinel_orchestrator
        gw = get_gateway()
        orch = init_sentinel_orchestrator(gw)
        import asyncio
        result = asyncio.run(orch.process("show system info", identity=TEST_IDENTITY))
        if result.decision is not None:
            assert hasattr(result.decision, "context_factors"), \
                "Decision must include context_factors field"

    def test_decision_with_execute_intent_includes_context_factors(self):
        from modules import get_gateway, init_sentinel_orchestrator
        gw = get_gateway()
        orch = init_sentinel_orchestrator(gw)
        import asyncio
        result = asyncio.run(orch.process("run command echo hello", identity=TEST_IDENTITY))
        assert result.decision is not None, \
            "Execute intents must go through DecisionEngine (should_skip_decision returns False)"
        assert hasattr(result.decision, "context_factors"), \
            "Decision must include context_factors even for execute intents"

    def test_whole_intent_plan_decision_flow(self):
        from modules import get_gateway, init_sentinel_orchestrator
        gw = get_gateway()
        orch = init_sentinel_orchestrator(gw)
        import asyncio
        result = asyncio.run(orch.process("cpu usage", identity=TEST_IDENTITY))
        assert result.plan is not None
        assert result.plan.intent.target == "system.cpu"
        assert result.plan.tool_id == "system.cpu"
        assert result.decision is None or result.decision.decision in ("approve", "reject", "require_confirm")
