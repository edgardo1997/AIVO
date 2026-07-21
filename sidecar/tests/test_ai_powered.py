import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch
import pytest

from sentinel.core.intent import IntentEngine, Intent
from sentinel.core.decision_engine import DecisionEngine, Decision
from sentinel.core.planner import Plan, PlanStep


class TestAIIntentEngine:
    def test_no_router_uses_regex_only(self):
        engine = IntentEngine()
        intent = engine.parse("show me the cpu")
        assert intent.target == "system.cpu"
        assert intent.confidence > 0.0

    def test_router_no_keys_uses_regex_only(self):
        router = MagicMock()
        router._key_map = {}
        engine = IntentEngine(model_router=router)
        intent = engine.parse("show me the cpu")
        assert intent.target == "system.cpu"

    def test_router_with_keys_called_when_regex_low(self):
        router = MagicMock()
        router._key_map = {"openrouter": "sk-test"}
        router.chat.return_value = {
            "response": json.dumps(
                {
                    "action": "analyze",
                    "target": "system.health",
                    "confidence": 0.85,
                    "parameters": {},
                    "reason": "User wants system analysis",
                }
            ),
            "provider": "openrouter",
        }
        engine = IntentEngine(model_router=router)
        intent = engine.parse("I want you to run a full diagnostic of my computer please")
        assert intent.action == "analyze"
        assert intent.target == "system.health"
        assert intent.confidence >= 0.8

    def test_llm_fallback_when_regex_beats_llm(self):
        router = MagicMock()
        router._key_map = {"openrouter": "sk-test"}
        router.chat.return_value = {
            "response": json.dumps(
                {
                    "action": "query",
                    "target": "unknown",
                    "confidence": 0.3,
                    "parameters": {},
                    "reason": "Unclear",
                }
            ),
        }
        engine = IntentEngine(model_router=router)
        intent = engine.parse("show cpu")
        assert intent.target == "system.cpu"
        assert intent.confidence >= 0.5

    def test_llm_fallback_handles_invalid_json(self):
        router = MagicMock()
        router._key_map = {"openrouter": "sk-test"}
        router.chat.return_value = {"response": "invalid json"}
        engine = IntentEngine(model_router=router)
        intent = engine.parse("gibberish text that does not match any pattern")
        assert intent is not None
        assert intent.confidence < 0.6

    def test_router_exception_falls_back_to_regex(self):
        router = MagicMock()
        router._key_map = {"openrouter": "sk-test"}
        router.chat.side_effect = RuntimeError("API down")
        engine = IntentEngine(model_router=router)
        intent = engine.parse("check memory")
        assert intent.target == "system.memory"

    def test_llm_with_context_hint(self):
        router = MagicMock()
        router._key_map = {"openrouter": "sk-test"}
        router.chat.return_value = {
            "response": json.dumps(
                {
                    "action": "analyze",
                    "target": "system.health",
                    "confidence": 0.9,
                    "parameters": {},
                }
            ),
        }
        engine = IntentEngine(model_router=router)
        context = {"system_summary": {"cpu_percent": 95, "memory_percent": 50}}
        intent = engine.parse("what's wrong with my PC", context)
        assert intent.action == "analyze"
        assert intent.target == "system.health"

    def test_llm_confidence_lower_than_regex_stays_regex(self):
        router = MagicMock()
        router._key_map = {"openrouter": "sk-test"}
        router.chat.return_value = {
            "response": json.dumps(
                {
                    "action": "query",
                    "target": "unknown",
                    "confidence": 0.1,
                }
            ),
        }
        engine = IntentEngine(model_router=router)
        intent = engine.parse("show cpu usage")
        assert intent.target == "system.cpu"


class TestAIDecisionEngine:
    def test_no_router_uses_rule_based(self):
        engine = DecisionEngine(get_permission_level=lambda: "admin")
        plan = Plan(
            intent=None, steps=[PlanStep(id="s1", tool_id="system.cpu", description="check cpu")], risk_score=0.1
        )
        result = engine.evaluate(plan)
        assert result.decision == Decision.APPROVE

    def test_router_no_keys_uses_rules(self):
        router = MagicMock()
        router._key_map = {}
        engine = DecisionEngine(get_permission_level=lambda: "admin", model_router=router)
        plan = Plan(
            intent=None, steps=[PlanStep(id="s1", tool_id="system.cpu", description="check cpu")], risk_score=0.1
        )
        result = engine.evaluate(plan)
        assert result.decision == Decision.APPROVE

    def test_llm_cannot_lower_objective_risk(self):
        router = MagicMock()
        router._key_map = {"openrouter": "sk-test"}
        router.chat.return_value = {
            "response": json.dumps(
                {
                    "risk_modifier": -0.2,
                    "reason": "Read-only query, safe to execute",
                    "warnings": [],
                }
            ),
        }
        engine = DecisionEngine(get_permission_level=lambda: "confirm", model_router=router)
        plan = Plan(
            intent=None, steps=[PlanStep(id="s1", tool_id="system.cpu", description="check cpu")], risk_score=0.5
        )
        result = engine.evaluate(plan)
        assert result.decision == Decision.REQUIRE_CONFIRM
        assert result.final_risk_score == 0.5

    def test_llm_cannot_raise_objective_risk(self):
        router = MagicMock()
        router._key_map = {"openrouter": "sk-test"}
        router.chat.return_value = {
            "response": json.dumps(
                {
                    "risk_modifier": 0.3,
                    "reason": "Extremely destructive operation",
                    "warnings": ["file deletion"],
                }
            ),
        }
        engine = DecisionEngine(get_permission_level=lambda: "confirm", model_router=router)
        plan = Plan(
            intent=None,
            steps=[
                PlanStep(
                    id="s1", tool_id="filesystem.write", description="delete system files", estimated_impact="critical"
                ),
            ],
            risk_score=0.5,
        )
        result = engine.evaluate(plan)
        assert result.decision == Decision.REQUIRE_CONFIRM
        assert result.final_risk_score == 0.5

    def test_llm_failure_uses_rule_based(self):
        router = MagicMock()
        router._key_map = {"openrouter": "sk-test"}
        router.chat.side_effect = RuntimeError("API error")
        engine = DecisionEngine(get_permission_level=lambda: "confirm", model_router=router)
        plan = Plan(
            intent=None, steps=[PlanStep(id="s1", tool_id="system.cpu", description="check cpu")], risk_score=0.1
        )
        result = engine.evaluate(plan)
        assert result.decision == Decision.APPROVE

    def test_llm_called_only_when_risk_exceeds_auto(self):
        router = MagicMock()
        router._key_map = {"openrouter": "sk-test"}
        engine = DecisionEngine(get_permission_level=lambda: "admin", model_router=router)
        plan = Plan(
            intent=None, steps=[PlanStep(id="s1", tool_id="system.cpu", description="check cpu")], risk_score=0.05
        )
        result = engine.evaluate(plan)
        router.chat.assert_not_called()
        assert result.decision == Decision.APPROVE

    @pytest.mark.asyncio
    async def test_llm_with_orchestrator_integration(self):
        """Full integration: Orchestrator with mock model_router wires to both engines."""
        from sentinel.core.orchestrator import Orchestrator
        from sentinel.core.tool_gateway import ToolGateway
        from sentinel.core.planner import Planner

        router = MagicMock()
        router._key_map = {"openrouter": "sk-test"}
        router.chat.return_value = {
            "response": json.dumps(
                {
                    "action": "query",
                    "target": "system.cpu",
                    "confidence": 0.9,
                }
            ),
        }

        intent_engine = IntentEngine(model_router=router)
        decision_engine = DecisionEngine(get_permission_level=lambda: "admin", model_router=router)

        orch = Orchestrator(
            intent_engine=intent_engine,
            tool_gateway=ToolGateway(),
            planner=Planner(),
            decision_engine=decision_engine,
            model_router=router,
            context_engine=None,
            memory=None,
        )
        assert orch._intent_engine._model_router is router
        assert orch._decision_engine._model_router is router
