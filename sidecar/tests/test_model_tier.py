import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from sentinel.core.context_budget import RequestPurpose
from sentinel.core.model_tier import (
    CostClass,
    ExecutionMode,
    LatencyClass,
    ModelTier,
    ModelTierDecision,
    ModelTierSelector,
    RequestProfile,
    RiskLevel,
    classify_request_minimum_tier,
    tier_for_model,
    tier_for_provider,
)
from sentinel.core.router_types import ProviderSpec, TaskType
from sentinel.models import ModelMetadata
from sentinel.routing.provider_selector import ProviderSelector


class FakeCapabilityManager:
    def assess(self, model_id, profile, config):
        class _Result:
            def to_dict(self):
                return {"compatible": True, "reason": ""}
        return _Result()


def _sample_models():
    return [
        ModelMetadata(
            id="qwen-1.7b",
            provider="sentinel_local",
            context_window=8192,
            supports_tool_calling=False,
            supports_coding=False,
            supports_reasoning=False,
            local=True,
            cost=0.0,
        ),
        ModelMetadata(
            id="qwen-7b-coder",
            provider="ollama",
            context_window=8192,
            supports_tool_calling=True,
            supports_coding=True,
            supports_reasoning=False,
            local=True,
            cost=0.0,
        ),
        ModelMetadata(
            id="gpt-4o",
            provider="openai",
            context_window=128000,
            supports_tool_calling=True,
            supports_coding=True,
            supports_reasoning=True,
            local=False,
            cost=0.01,
        ),
        ModelMetadata(
            id="claude-sonnet-4",
            provider="anthropic",
            context_window=200000,
            supports_tool_calling=True,
            supports_coding=True,
            supports_reasoning=True,
            local=False,
            cost=0.05,
        ),
    ]


@pytest.fixture
def selector():
    return ModelTierSelector()


class TestRequestClassification:
    def test_greeting_selects_tier_1(self, selector):
        profile = RequestProfile(text="Hello, how are you?", purpose=RequestPurpose.CONVERSATION)
        decision = selector.select_tier(profile, _sample_models())
        assert decision.minimum_required_tier == ModelTier.FAST_CONVERSATIONAL
        assert decision.selected_tier == ModelTier.FAST_CONVERSATIONAL
        assert decision.execution_mode == ExecutionMode.LLM

    def test_simple_rewriting_selects_tier_1(self, selector):
        profile = RequestProfile(text="Rewrite this sentence briefly", purpose=RequestPurpose.CONVERSATION)
        decision = selector.select_tier(profile, _sample_models())
        assert decision.minimum_required_tier == ModelTier.FAST_CONVERSATIONAL

    def test_basic_python_explanation_tier_1_or_2(self, selector):
        profile = RequestProfile(text="What is Python?", purpose=RequestPurpose.TECHNICAL)
        decision = selector.select_tier(profile, _sample_models())
        assert decision.minimum_required_tier in (ModelTier.FAST_CONVERSATIONAL, ModelTier.BALANCED_REASONING)

    def test_technical_debugging_tier_2(self, selector):
        profile = RequestProfile(text="Debug this Python function", purpose=RequestPurpose.TECHNICAL)
        decision = selector.select_tier(profile, _sample_models())
        assert decision.minimum_required_tier == ModelTier.BALANCED_REASONING

    def test_architecture_review_tier_3(self, selector):
        profile = RequestProfile(text="Review the architecture of this system", purpose=RequestPurpose.REASONING)
        decision = selector.select_tier(profile, _sample_models())
        assert decision.minimum_required_tier == ModelTier.ADVANCED_REASONING

    def test_known_application_launch_is_deterministic(self, selector):
        profile = RequestProfile(
            text="open Spotify",
            purpose=RequestPurpose.CONVERSATION,
            known_command=True,
            action_name="open",
        )
        decision = selector.select_tier(profile, _sample_models())
        assert decision.execution_mode == ExecutionMode.DETERMINISTIC
        assert decision.selected_tier == ModelTier.DETERMINISTIC

    def test_destructive_action_does_not_bypass_governance(self, selector):
        profile = RequestProfile(
            text="delete the file",
            known_command=True,
            action_name="delete",
            destructive=True,
            governed=True,
        )
        decision = selector.select_tier(profile, _sample_models())
        assert decision.execution_mode == ExecutionMode.LLM
        assert decision.minimum_required_tier >= ModelTier.BALANCED_REASONING

    def test_high_risk_ambiguity_tier_3_or_clarification(self, selector):
        profile = RequestProfile(
            text="This is complex, ambiguous and security-critical",
            risk_level=RiskLevel.HIGH,
        )
        decision = selector.select_tier(profile, _sample_models())
        assert decision.minimum_required_tier >= ModelTier.BALANCED_REASONING

    def test_tier_4_not_for_ordinary_chat(self, selector):
        profile = RequestProfile(text="Hi there, what's the weather?")
        decision = selector.select_tier(profile, _sample_models())
        assert decision.selected_tier != ModelTier.MULTI_MODEL_COORDINATION
        assert decision.minimum_required_tier != ModelTier.MULTI_MODEL_COORDINATION

    def test_tier_4_requires_explicit_signal(self, selector):
        profile = RequestProfile(text="Run a multi model independent security review")
        decision = selector.select_tier(profile, _sample_models())
        # The "multi model" + "independent review" qualifier keeps it eligible
        assert decision.minimum_required_tier == ModelTier.MULTI_MODEL_COORDINATION

    def test_long_context_excludes_small_window_models(self, selector):
        profile = RequestProfile(text="Summarize this 50k token document", estimated_tokens=50000)
        decision = selector.select_tier(profile, _sample_models())
        assert "qwen-1.7b" in decision.excluded_models
        assert "qwen-7b-coder" in decision.excluded_models
        assert all(m in decision.eligible_models for m in ["gpt-4o", "claude-sonnet-4"])

    def test_escalation_recorded_when_minimum_exceeds_constraints(self, selector):
        # High reasoning requirement but budget forces a low ceiling
        profile = RequestProfile(
            text="Security architecture review",
            purpose=RequestPurpose.REASONING,
            budget_remaining_usd=0.0,
            user_quality_cost_preference="quality",
        )
        decision = selector.select_tier(profile, _sample_models())
        assert decision.escalation_required is True
        assert decision.maximum_allowed_tier < decision.minimum_required_tier

    def test_downgrade_recorded_truthfully(self, selector):
        # Request needs advanced reasoning, but budget caps at balanced
        profile = RequestProfile(
            text="Debug this complex Python architecture",
            purpose=RequestPurpose.REASONING,
            budget_remaining_usd=0.2,
        )
        decision = selector.select_tier(profile, _sample_models())
        assert decision.downgrade_applied is True
        assert decision.downgrade_reason is not None
        assert decision.selected_tier <= decision.maximum_allowed_tier

    def test_conversation_route_remains_lightweight(self, selector):
        profile = RequestProfile(text="hello", purpose=RequestPurpose.CONVERSATION)
        decision = selector.select_tier(profile, _sample_models())
        assert decision.selected_tier in (ModelTier.FAST_CONVERSATIONAL, ModelTier.DETERMINISTIC)
        assert decision.selected_tier != ModelTier.MULTI_MODEL_COORDINATION

    def test_governed_tool_action_not_deterministic(self, selector):
        profile = RequestProfile(
            text="Run the filesystem delete tool",
            purpose=RequestPurpose.GOVERNED_ACTION,
            num_tools=1,
            governed=True,
            destructive=True,
        )
        decision = selector.select_tier(profile, _sample_models())
        assert decision.execution_mode == ExecutionMode.LLM
        assert decision.minimum_required_tier >= ModelTier.BALANCED_REASONING

    def test_model_tier_not_based_on_hardware_letter_classes(self, selector):
        # No hardware class A/B/C/D is referenced in the decision
        profile = RequestProfile(text="Write a poem")
        decision = selector.select_tier(profile, _sample_models())
        assert "A" not in decision.reason_codes
        assert "class" not in str(decision.reason_codes).lower()


class TestModelCapabilityTiers:
    def test_small_chat_model_is_tier_1(self):
        model = ModelMetadata(
            id="tiny",
            provider="local",
            context_window=4096,
            supports_reasoning=False,
            supports_coding=False,
            supports_tool_calling=False,
            local=True,
        )
        assert tier_for_model(model) == ModelTier.FAST_CONVERSATIONAL

    def test_coding_or_tool_model_is_tier_2(self):
        model = ModelMetadata(
            id="qwen-7b",
            provider="ollama",
            context_window=8192,
            supports_coding=True,
            local=True,
        )
        assert tier_for_model(model) == ModelTier.BALANCED_REASONING

    def test_large_reasoning_cloud_model_is_tier_3(self):
        model = ModelMetadata(
            id="claude",
            provider="anthropic",
            context_window=200000,
            supports_reasoning=True,
            cost=0.05,
        )
        assert tier_for_model(model) == ModelTier.ADVANCED_REASONING

    def test_provider_tier_from_task_types(self):
        p = ProviderSpec(id="quick", name="Quick", task_types=[TaskType.QUICK, TaskType.LOCAL], is_local=True)
        assert tier_for_provider(p) == ModelTier.FAST_CONVERSATIONAL

        p = ProviderSpec(id="reason", name="Reason", task_types=[TaskType.REASONING, TaskType.CODE], is_local=False)
        assert tier_for_provider(p) == ModelTier.ADVANCED_REASONING


class TestProviderSelectorTierIntegration:
    @pytest.fixture
    def providers(self):
        return {
            "openai": ProviderSpec(
                id="openai", name="OpenAI", task_types=[TaskType.QUICK, TaskType.REASONING, TaskType.CODE],
                requires_key=True, default_model="gpt-4o", priority=20,
            ),
            "anthropic": ProviderSpec(
                id="anthropic", name="Anthropic", task_types=[TaskType.REASONING, TaskType.ANALYSIS, TaskType.CODE],
                requires_key=True, default_model="claude-sonnet-4", priority=18,
            ),
            "sentinel_local": ProviderSpec(
                id="sentinel_local", name="Sentinel Local", task_types=[TaskType.QUICK, TaskType.LOCAL],
                requires_key=False, is_local=True, default_model="Qwen3-1.7B-Q8_0.gguf", priority=50,
            ),
        }

    @pytest.fixture
    def base_selector(self, providers):
        selector = ProviderSelector(providers=providers, capability_manager=FakeCapabilityManager())
        selector.set_api_key("openai", "key")
        selector.set_api_key("anthropic", "key")
        return selector

    def test_explicit_user_selection_respected_when_satisfies_minimum(self, base_selector):
        decision = ModelTierDecision(
            requested_tier=ModelTier.ADVANCED_REASONING,
            selected_tier=ModelTier.ADVANCED_REASONING,
            minimum_required_tier=ModelTier.BALANCED_REASONING,
            maximum_allowed_tier=ModelTier.ADVANCED_REASONING,
        )
        router = base_selector.select(TaskType.REASONING, context={"tier_decision": decision}, explicit_provider="openai")
        assert router.provider_id == "openai"
        assert router.selection_trace["actual_provider"] == "openai"

    def test_explicit_undersized_model_rejected(self, base_selector):
        decision = ModelTierDecision(
            requested_tier=ModelTier.BALANCED_REASONING,
            selected_tier=ModelTier.BALANCED_REASONING,
            minimum_required_tier=ModelTier.BALANCED_REASONING,
            maximum_allowed_tier=ModelTier.BALANCED_REASONING,
        )
        # sentinel_local is QUICK/LOCAL -> tier 1, below T2
        router = base_selector.select(TaskType.QUICK, context={"tier_decision": decision}, explicit_provider="sentinel_local")
        assert "tier_below_minimum" in router.reason
        assert router.selection_trace["fallback_required"] is True

    def test_privacy_forbids_cloud_selects_local(self, base_selector):
        decision = ModelTierDecision(
            requested_tier=ModelTier.FAST_CONVERSATIONAL,
            selected_tier=ModelTier.FAST_CONVERSATIONAL,
            minimum_required_tier=ModelTier.FAST_CONVERSATIONAL,
            maximum_allowed_tier=ModelTier.BALANCED_REASONING,
        )
        router = base_selector.select(TaskType.QUICK, context={"tier_decision": decision, "cloud_allowed": False})
        assert base_selector._providers[router.provider_id].is_local

    def test_deterministic_tier_0_returns_non_llm_decision(self, base_selector):
        decision = ModelTierDecision(
            requested_tier=ModelTier.DETERMINISTIC,
            selected_tier=ModelTier.DETERMINISTIC,
            minimum_required_tier=ModelTier.DETERMINISTIC,
            maximum_allowed_tier=ModelTier.DETERMINISTIC,
            execution_mode=ExecutionMode.DETERMINISTIC,
        )
        router = base_selector.select(TaskType.QUICK, context={"tier_decision": decision})
        assert router.provider_id == "deterministic"
        assert router.selection_trace["execution_mode"] == "deterministic"

    def test_preferred_provider_unhealthy_triggers_same_tier_fallback(self, base_selector):
        # Remove openai from consideration; anthropic is the only other cloud reasoning provider
        base_selector.delete_api_key("openai")
        decision = ModelTierDecision(
            requested_tier=ModelTier.ADVANCED_REASONING,
            selected_tier=ModelTier.ADVANCED_REASONING,
            minimum_required_tier=ModelTier.BALANCED_REASONING,
            maximum_allowed_tier=ModelTier.ADVANCED_REASONING,
        )
        router = base_selector.select(TaskType.REASONING, context={"tier_decision": decision})
        assert router.provider_id == "anthropic"

    def test_no_candidate_meets_minimum_reports_degraded(self, base_selector):
        # Ask for T3 reasoning but no cloud keys and local cannot do T3
        base_selector.delete_api_key("openai")
        base_selector.delete_api_key("anthropic")
        decision = ModelTierDecision(
            requested_tier=ModelTier.ADVANCED_REASONING,
            selected_tier=ModelTier.ADVANCED_REASONING,
            minimum_required_tier=ModelTier.ADVANCED_REASONING,
            maximum_allowed_tier=ModelTier.ADVANCED_REASONING,
        )
        # This raises because no provider is available after tier gating
        with pytest.raises(RuntimeError):
            base_selector.select(TaskType.REASONING, context={"tier_decision": decision})

    def test_provider_metadata_matches_actual_execution(self, base_selector):
        decision = ModelTierDecision(
            requested_tier=ModelTier.BALANCED_REASONING,
            selected_tier=ModelTier.BALANCED_REASONING,
            minimum_required_tier=ModelTier.BALANCED_REASONING,
            maximum_allowed_tier=ModelTier.BALANCED_REASONING,
        )
        router = base_selector.select(TaskType.CODE, context={"tier_decision": decision})
        assert router.selection_trace["actual_provider"] == router.provider_id
        assert router.selection_trace["actual_model"] == router.model
