import pytest
from unittest.mock import MagicMock, patch
from sentinel.core.intelligence_orchestrator import (
    IntelligenceOrchestrator,
    IntelligenceDecision,
    ExecutionStrategy,
    INTENT_STRATEGY_MAP,
)
from sentinel.core.intent_engine_v2 import ClassifiedIntent, IntentCategory
from sentinel.core.capability_engine import CapabilityEngine, CapabilitySet
from sentinel.core.model_registry import ModelRegistry
from sentinel.models import ModelMetadata, ModelStatus


def _make_registry():
    registry = ModelRegistry()
    registry.register_many([
        ModelMetadata(id="tool-caller", provider="deepseek", supports_tool_calling=True, supports_coding=True, supports_reasoning=True, cost=0.0, local=False, speed="fast", status=ModelStatus.AVAILABLE),
        ModelMetadata(id="chat-only", provider="test", supports_tool_calling=False, supports_coding=False, supports_reasoning=False, cost=0.0, local=True, speed="fast", status=ModelStatus.AVAILABLE),
        ModelMetadata(id="local-coder", provider="ollama", supports_tool_calling=False, supports_coding=True, supports_reasoning=True, cost=0.0, local=True, speed="slow", status=ModelStatus.AVAILABLE),
        ModelMetadata(id="premium", provider="openai", supports_tool_calling=True, supports_coding=True, supports_reasoning=True, cost=5.0, local=False, speed="fast", status=ModelStatus.AVAILABLE),
    ])
    return registry


class TestExecutionStrategy:
    def test_all_categories_have_strategies(self):
        for cat in IntentCategory:
            assert cat in INTENT_STRATEGY_MAP
            assert isinstance(INTENT_STRATEGY_MAP[cat], ExecutionStrategy)

    def test_strategy_values(self):
        assert ExecutionStrategy.CHAT_ONLY.value == "chat_only"
        assert ExecutionStrategy.TOOL_EXECUTION.value == "tool_execution"
        assert ExecutionStrategy.REASONING.value == "reasoning"
        assert ExecutionStrategy.CODING.value == "coding"
        assert ExecutionStrategy.MULTI_STEP.value == "multi_step"

    def test_chat_strategy(self):
        assert INTENT_STRATEGY_MAP[IntentCategory.CHAT] == ExecutionStrategy.CHAT_ONLY

    def test_action_strategy(self):
        assert INTENT_STRATEGY_MAP[IntentCategory.ACTION] == ExecutionStrategy.TOOL_EXECUTION

    def test_coding_strategy(self):
        assert INTENT_STRATEGY_MAP[IntentCategory.CODING] == ExecutionStrategy.CODING

    def test_reasoning_strategy(self):
        assert INTENT_STRATEGY_MAP[IntentCategory.REASONING] == ExecutionStrategy.REASONING


class TestIntelligenceDecision:
    def test_default_decision(self):
        d = IntelligenceDecision()
        assert d.status == "success"
        assert d.execution_strategy == ExecutionStrategy.CHAT_ONLY
        assert d.model_id == ""

    def test_to_dict(self):
        d = IntelligenceDecision(
            model_id="tool-caller",
            provider="deepseek",
            required_capabilities=["tool_calling", "system_access"],
            execution_strategy=ExecutionStrategy.TOOL_EXECUTION,
            confidence=0.94,
            reasoning="Best match",
        )
        dd = d.to_dict()
        assert dd["model_id"] == "tool-caller"
        assert dd["execution_strategy"] == "tool_execution"
        assert dd["confidence"] == 0.94
        assert dd["status"] == "success"


class TestIntelligenceOrchestrator:
    def test_orchestrate_action(self):
        registry = _make_registry()
        cap_engine = CapabilityEngine()
        orch = IntelligenceOrchestrator(model_registry=registry, capability_engine=cap_engine)
        intent = ClassifiedIntent(category=IntentCategory.ACTION, target="spotify", confidence=0.95, source="rule")
        decision = orch.orchestrate(intent)
        assert decision.status == "success"
        assert decision.execution_strategy == ExecutionStrategy.TOOL_EXECUTION
        assert decision.model_id != ""
        assert "tool_calling" in decision.required_capabilities

    def test_orchestrate_chat(self):
        registry = _make_registry()
        orch = IntelligenceOrchestrator(model_registry=registry)
        intent = ClassifiedIntent(category=IntentCategory.CHAT, target="", confidence=0.95, source="rule")
        decision = orch.orchestrate(intent)
        assert decision.status == "success"
        assert decision.execution_strategy == ExecutionStrategy.CHAT_ONLY
        assert decision.selected_tools == []

    def test_orchestrate_coding(self):
        registry = _make_registry()
        cap_engine = CapabilityEngine()
        orch = IntelligenceOrchestrator(model_registry=registry, capability_engine=cap_engine)
        intent = ClassifiedIntent(category=IntentCategory.CODING, target="", confidence=0.92, source="rule")
        decision = orch.orchestrate(intent)
        assert decision.status == "success"
        assert decision.execution_strategy == ExecutionStrategy.CODING
        assert "coding" in decision.required_capabilities

    def test_orchestrate_reasoning(self):
        registry = _make_registry()
        orch = IntelligenceOrchestrator(model_registry=registry)
        intent = ClassifiedIntent(category=IntentCategory.REASONING, target="", confidence=0.88, source="rule")
        decision = orch.orchestrate(intent)
        assert decision.status == "success"
        assert decision.execution_strategy == ExecutionStrategy.REASONING

    def test_no_capable_model(self):
        registry = ModelRegistry()
        registry.register(ModelMetadata(id="no-cap", provider="test", supports_tool_calling=False, supports_coding=False, cost=0.0, status=ModelStatus.AVAILABLE))
        cap_engine = CapabilityEngine()
        orch = IntelligenceOrchestrator(model_registry=registry, capability_engine=cap_engine)
        intent = ClassifiedIntent(category=IntentCategory.ACTION, target="spotify", confidence=0.95, source="rule")
        decision = orch.orchestrate(intent)
        assert decision.status == "no_capable_model"
        assert decision.model_id == ""

    def test_no_registry(self):
        orch = IntelligenceOrchestrator()
        intent = ClassifiedIntent(category=IntentCategory.CHAT, target="", confidence=0.9, source="rule")
        decision = orch.orchestrate(intent)
        assert decision.status == "no_registry"

    def test_action_selects_tool_calling_model(self):
        registry = _make_registry()
        cap_engine = CapabilityEngine()
        orch = IntelligenceOrchestrator(model_registry=registry, capability_engine=cap_engine)
        intent = ClassifiedIntent(category=IntentCategory.ACTION, target="chrome", confidence=0.95, source="rule")
        decision = orch.orchestrate(intent)
        assert decision.model_id in ("tool-caller", "premium")
        model = registry.get(decision.model_id)
        assert model is not None
        assert model.supports_tool_calling is True

    def test_coding_selects_coding_model(self):
        registry = _make_registry()
        cap_engine = CapabilityEngine()
        orch = IntelligenceOrchestrator(model_registry=registry, capability_engine=cap_engine)
        intent = ClassifiedIntent(category=IntentCategory.CODING, target="", confidence=0.95, source="rule")
        decision = orch.orchestrate(intent)
        model = registry.get(decision.model_id)
        assert model is not None
        assert model.supports_coding is True

    def test_tools_selected_for_tool_execution(self):
        registry = _make_registry()
        cap_engine = CapabilityEngine()
        orch = IntelligenceOrchestrator(model_registry=registry, capability_engine=cap_engine)
        intent = ClassifiedIntent(category=IntentCategory.ACTION, target="chrome", confidence=0.95, source="rule")
        mock_tools = [MagicMock(), MagicMock()]
        mock_tools[0].id = "executor.launch"
        mock_tools[1].id = "executor.kill"
        decision = orch.orchestrate(intent, available_tools=mock_tools)
        assert len(decision.selected_tools) == 2
        assert "executor.launch" in decision.selected_tools

    def test_no_tools_for_chat_strategy(self):
        registry = _make_registry()
        orch = IntelligenceOrchestrator(model_registry=registry)
        intent = ClassifiedIntent(category=IntentCategory.CHAT, target="", confidence=0.95, source="rule")
        mock_tools = [MagicMock()]
        mock_tools[0].id = "executor.launch"
        decision = orch.orchestrate(intent, available_tools=mock_tools)
        assert decision.selected_tools == []

    def test_scoring_prefers_low_cost(self):
        registry = ModelRegistry()
        registry.register_many([
            ModelMetadata(id="cheap", provider="test", supports_tool_calling=True, cost=0.0, status=ModelStatus.AVAILABLE),
            ModelMetadata(id="expensive", provider="test", supports_tool_calling=True, cost=10.0, status=ModelStatus.AVAILABLE),
        ])
        cap_engine = CapabilityEngine()
        orch = IntelligenceOrchestrator(model_registry=registry, capability_engine=cap_engine)
        intent = ClassifiedIntent(category=IntentCategory.ACTION, target="x", confidence=0.95, source="rule")
        decision = orch.orchestrate(intent)
        assert decision.model_id == "cheap"

    def test_set_model_registry(self):
        orch = IntelligenceOrchestrator()
        registry = _make_registry()
        orch.set_model_registry(registry)
        intent = ClassifiedIntent(category=IntentCategory.CHAT, target="", confidence=0.9, source="rule")
        decision = orch.orchestrate(intent)
        assert decision.status == "success"

    def test_set_capability_engine(self):
        orch = IntelligenceOrchestrator()
        cap_engine = CapabilityEngine()
        orch.set_capability_engine(cap_engine)
        intent = ClassifiedIntent(category=IntentCategory.ACTION, target="x", confidence=0.9, source="rule")
        from sentinel.core.model_registry import ModelRegistry
        registry = _make_registry()
        orch.set_model_registry(registry)
        decision = orch.orchestrate(intent)
        assert "tool_calling" in decision.required_capabilities

    def test_reasoning_includes_model_info(self):
        registry = _make_registry()
        orch = IntelligenceOrchestrator(model_registry=registry)
        intent = ClassifiedIntent(category=IntentCategory.ACTION, target="notepad", confidence=0.95, source="rule", raw_input="abre notepad")
        decision = orch.orchestrate(intent)
        assert "Intent: ACTION" in decision.reasoning
        assert "Model:" in decision.reasoning
        assert "Capabilities:" in decision.reasoning

    def test_decision_to_dict_complete(self):
        registry = _make_registry()
        cap_engine = CapabilityEngine()
        orch = IntelligenceOrchestrator(model_registry=registry, capability_engine=cap_engine)
        intent = ClassifiedIntent(category=IntentCategory.CODING, target="", confidence=0.9, source="rule")
        decision = orch.orchestrate(intent)
        dd = decision.to_dict()
        assert all(k in dd for k in ("model_id", "provider", "required_capabilities", "execution_strategy", "confidence", "reasoning", "status"))

    def test_tool_execution_rejects_models_without_tool_calling(self):
        registry = ModelRegistry()
        registry.register(ModelMetadata(id="no-tools", provider="test", supports_tool_calling=False, status=ModelStatus.AVAILABLE))
        cap_engine = CapabilityEngine()
        orch = IntelligenceOrchestrator(model_registry=registry, capability_engine=cap_engine)
        intent = ClassifiedIntent(category=IntentCategory.ACTION, target="x", confidence=0.95, source="rule")
        decision = orch.orchestrate(intent)
        assert decision.status == "no_capable_model"
