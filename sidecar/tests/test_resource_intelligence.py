import pytest
from sentinel.core.resource_intelligence import (
    ResourceIntelligenceLayer,
    ResourceDecision,
    SystemSnapshot,
    CLOUD_PROVIDERS,
)


class FakeModel:
    def __init__(self, id="test", provider="local", local=False, cost=0.0, speed="fast", coding=False, reasoning=False):
        self.id = id
        self.provider = provider
        self.local = local
        self.cost = cost
        self.speed = speed
        self.supports_coding = coding
        self.supports_reasoning = reasoning
        self.supports_tool_calling = False
        self.supports_vision = False
        self.supports_embeddings = False
        self.status = "available"

    def has_capability(self, cap):
        return getattr(self, f"supports_{cap}", False)


class TestSystemSnapshot:
    def test_ram_percentage(self):
        s = SystemSnapshot(ram_available_gb=8, ram_total_gb=32)
        assert s.ram_available_pct == 25.0

    def test_low_resources_ram(self):
        s = SystemSnapshot(ram_available_gb=2, ram_total_gb=32)
        assert s.low_resources is True

    def test_low_resources_battery(self):
        s = SystemSnapshot(on_battery=True, battery_percent=10)
        assert s.low_resources is True

    def test_low_resources_power_saver(self):
        s = SystemSnapshot(power_saver_active=True)
        assert s.low_resources is True

    def test_not_low_resources(self):
        s = SystemSnapshot(ram_available_gb=16, ram_total_gb=32)
        assert s.low_resources is False

    def test_to_dict(self):
        s = SystemSnapshot(online=True, ram_available_gb=8.0)
        d = s.to_dict()
        assert d["online"] is True
        assert d["ram_available_gb"] == 8.0


class TestResourceDecision:
    def test_defaults(self):
        d = ResourceDecision()
        assert d.allowed is True
        assert d.score_modifier == 0

    def test_rejected(self):
        d = ResourceDecision(allowed=False, reason="no RAM", score_modifier=-100)
        assert d.allowed is False
        assert d.reason == "no RAM"

    def test_to_dict(self):
        d = ResourceDecision(allowed=True, reason="fast", score_modifier=20)
        r = d.to_dict()
        assert r["allowed"] is True
        assert r["reason"] == "fast"
        assert r["score_modifier"] == 20


class TestResourceIntelligenceLayer:
    def test_cloud_model_offline_rejected(self):
        """Test 1: Cloud model rejected when offline."""
        ri = ResourceIntelligenceLayer()
        state = SystemSnapshot(online=False)
        model = FakeModel(id="gpt-4o", provider="openai", local=False)
        decision = ri.evaluate(model, state)
        assert decision.allowed is False
        assert "offline" in decision.reason.lower()

    def test_local_model_offline_allowed(self):
        """Test 1b: Local model allowed when offline."""
        ri = ResourceIntelligenceLayer()
        state = SystemSnapshot(online=False)
        model = FakeModel(id="qwen-local", provider="local", local=True)
        decision = ri.evaluate(model, state)
        assert decision.allowed is True

    def test_insufficient_ram_rejected(self):
        """Test 2: Model rejected when RAM insufficient."""
        ri = ResourceIntelligenceLayer()
        state = SystemSnapshot(ram_available_gb=4, ram_total_gb=8)
        model = FakeModel(id="llama-70b", provider="local", local=True)
        decision = ri.evaluate(model, state)
        assert decision.allowed is False
        assert "ram" in decision.reason.lower()

    def test_cloud_providers_set(self):
        assert "openai" in CLOUD_PROVIDERS
        assert "anthropic" in CLOUD_PROVIDERS
        assert "local" not in CLOUD_PROVIDERS

    def test_sufficient_ram_allowed(self):
        ri = ResourceIntelligenceLayer()
        state = SystemSnapshot(ram_available_gb=64, ram_total_gb=128)
        model = FakeModel(id="llama-70b", provider="local", local=True)
        decision = ri.evaluate(model, state)
        assert decision.allowed is True

    def test_evaluate_all_filters_rejected(self):
        ri = ResourceIntelligenceLayer()
        state = SystemSnapshot(online=False)
        models = [
            FakeModel(id="gpt-4o", provider="openai", local=False),
            FakeModel(id="qwen-local", provider="local", local=True),
        ]
        results = ri.evaluate_all(models, state)
        assert len(results) == 2
        cloud_decision = results[0][1]
        local_decision = results[1][1]
        assert cloud_decision.allowed is False
        assert local_decision.allowed is True

    def test_filter_candidates_rejects_offline_cloud(self):
        ri = ResourceIntelligenceLayer()
        state = SystemSnapshot(online=False)
        models = [
            FakeModel(id="gpt-4o", provider="openai", local=False),
            FakeModel(id="qwen-local", provider="local", local=True),
        ]
        filtered = ri.filter_candidates(models, state)
        assert len(filtered) == 1
        assert filtered[0][0].id == "qwen-local"

    def test_scoring_local_model_gets_bonus_when_offline(self):
        ri = ResourceIntelligenceLayer()
        state = SystemSnapshot(online=False)
        model = FakeModel(id="qwen-local", provider="local", local=True)
        decision = ri.evaluate(model, state)
        assert decision.score_modifier > 0
        assert decision.allowed is True

    def test_scoring_local_model_gets_bonus_on_battery(self):
        ri = ResourceIntelligenceLayer()
        state = SystemSnapshot(on_battery=True, battery_percent=50)
        model = FakeModel(id="qwen-local", provider="local", local=True)
        decision = ri.evaluate(model, state)
        assert decision.score_modifier > 0

    def test_scoring_cloud_model_penalty_on_battery(self):
        ri = ResourceIntelligenceLayer()
        state = SystemSnapshot(on_battery=True, battery_percent=50)
        model = FakeModel(id="gpt-4o", provider="openai", local=False)
        decision = ri.evaluate(model, state)
        assert decision.score_modifier < 0

    def test_budget_exceeded_rejected(self):
        ri = ResourceIntelligenceLayer()
        state = SystemSnapshot(has_budget_constraint=True, budget_remaining_usd=0.05)
        model = FakeModel(id="gpt-4o", provider="openai", local=False, cost=1.0)
        decision = ri.evaluate(model, state)
        assert decision.allowed is False
        assert "budget" in decision.reason.lower()

    def test_free_model_budget_ok(self):
        ri = ResourceIntelligenceLayer()
        state = SystemSnapshot(has_budget_constraint=True, budget_remaining_usd=0.05)
        model = FakeModel(id="qwen-local", provider="local", local=True, cost=0.0)
        decision = ri.evaluate(model, state)
        assert decision.allowed is True

    def test_slow_model_penalty(self):
        ri = ResourceIntelligenceLayer()
        state = SystemSnapshot()
        fast = FakeModel(id="fast", provider="local", local=True, speed="fast")
        slow = FakeModel(id="slow", provider="local", local=True, speed="slow")
        fast_d = ri.evaluate(fast, state)
        slow_d = ri.evaluate(slow, state)
        assert slow_d.score_modifier < fast_d.score_modifier

    def test_high_cpu_penalty(self):
        ri = ResourceIntelligenceLayer()
        low_cpu = SystemSnapshot(cpu_load_pct=10)
        high_cpu = SystemSnapshot(cpu_load_pct=90)
        model = FakeModel(id="test-model", provider="local", local=True)
        low_d = ri.evaluate(model, low_cpu)
        high_d = ri.evaluate(model, high_cpu)
        assert high_d.score_modifier < low_d.score_modifier

    def test_low_ram_penalty(self):
        ri = ResourceIntelligenceLayer()
        enough_ram = SystemSnapshot(ram_available_gb=16, ram_total_gb=32)
        low_ram = SystemSnapshot(ram_available_gb=2, ram_total_gb=16)
        model = FakeModel(id="test-model", provider="local", local=True)
        enough_d = ri.evaluate(model, enough_ram)
        low_d = ri.evaluate(model, low_ram)
        assert low_d.score_modifier < enough_d.score_modifier

    def test_fallback_when_best_rejected(self):
        """Test 5: Fallback to secondary model when primary is rejected."""
        ri = ResourceIntelligenceLayer()
        state = SystemSnapshot(online=False)
        models = [
            FakeModel(id="gpt-4o", provider="openai", local=False),
            FakeModel(id="qwen-local", provider="local", local=True),
        ]
        rejected_ids = {"gpt-4o"}
        result = ri.find_fallback(models, rejected_ids, state)
        assert result is not None
        assert result[0].id == "qwen-local"

    def test_no_fallback_when_all_rejected(self):
        ri = ResourceIntelligenceLayer()
        state = SystemSnapshot(online=False)
        models = [
            FakeModel(id="gpt-4o", provider="openai", local=False),
            FakeModel(id="claude", provider="anthropic", local=False),
        ]
        rejected_ids = set()
        result = ri.find_fallback(models, rejected_ids, state)
        assert result is None

    def test_snapshot_low_resources_true(self):
        s = SystemSnapshot(ram_available_gb=2, ram_total_gb=32)
        assert s.low_resources is True

    def test_snapshot_zero_ram_division(self):
        s = SystemSnapshot(ram_available_gb=0, ram_total_gb=0)
        assert s.ram_available_pct == 100.0

    def test_cloud_provider_detection(self):
        ri = ResourceIntelligenceLayer()
        state = SystemSnapshot(online=True)
        model = FakeModel(id="gpt-4o", provider="openai", local=False)
        decision = ri.evaluate(model, state)
        assert decision.allowed is True

    def test_cloud_provider_no_internet(self):
        ri = ResourceIntelligenceLayer()
        state = SystemSnapshot(online=False)
        model = FakeModel(id="claude", provider="anthropic", local=False)
        decision = ri.evaluate(model, state)
        assert decision.allowed is False

    def test_default_snapshot_online(self):
        ri = ResourceIntelligenceLayer()
        model = FakeModel(id="gpt-4o", provider="openai", local=False)
        decision = ri.evaluate(model)
        assert decision.allowed is True  # default state is online

    def test_gpu_vram_check(self):
        ri = ResourceIntelligenceLayer()
        state = SystemSnapshot(gpu_available=True, gpu_memory_free_mb=2000)
        model = FakeModel(id="llama-13b", provider="local", local=True)
        decision = ri.evaluate(model, state)
        assert decision.allowed is False
        assert "vram" in decision.reason.lower()


# ─────────────────────────────────────────────
# Integration with IntelligenceOrchestrator
# ─────────────────────────────────────────────
from sentinel.core.intelligence_orchestrator import IntelligenceOrchestrator, ExecutionStrategy
from sentinel.core.intent_engine_v2 import ClassifiedIntent, IntentCategory
from sentinel.core.capability_engine import CapabilityEngine, CapabilitySet
from sentinel.core.model_registry import ModelRegistry
from sentinel.models import ModelMetadata, ModelStatus


class TestOrchestratorIntegration:
    def test_resource_intelligence_rejects_cloud_when_offline(self):
        ri = ResourceIntelligenceLayer()
        registry = ModelRegistry()
        registry.register_many([
            ModelMetadata(id="cloud-model", provider="openai", supports_coding=True, supports_reasoning=True, cost=0.0, local=False, status=ModelStatus.AVAILABLE),
            ModelMetadata(id="local-model", provider="local", supports_coding=True, supports_reasoning=True, cost=0.0, local=True, status=ModelStatus.AVAILABLE),
        ])
        import sentinel.core.resource_intelligence as ri_module
        original = ri_module.ResourceIntelligenceLayer.evaluate
        original_snapshot = ri_module.ResourceIntelligenceLayer.snapshot

        def mock_evaluate(self, model, state=None):
            is_cloud = getattr(model, "provider", "") in ri_module.CLOUD_PROVIDERS
            if is_cloud:
                return ResourceDecision(allowed=False, reason="offline simulation", score_modifier=-100)
            return ResourceDecision(allowed=True, reason="compatible", score_modifier=0)

        def mock_snapshot(self):
            return SystemSnapshot(online=False)

        ri_module.ResourceIntelligenceLayer.evaluate = mock_evaluate
        ri_module.ResourceIntelligenceLayer.snapshot = mock_snapshot
        try:
            orch = IntelligenceOrchestrator(model_registry=registry)
            orch.set_resource_intelligence(ri)
            intent = ClassifiedIntent(category=IntentCategory.CODING, confidence=0.9, source="test")
            decision = orch.orchestrate(intent)
            assert decision.status == "success", f"Expected success, got {decision.status}: {decision.reasoning}"
            assert decision.model_id == "local-model"
        finally:
            ri_module.ResourceIntelligenceLayer.evaluate = original
            ri_module.ResourceIntelligenceLayer.snapshot = original_snapshot

    def test_resource_intelligence_blocks_all_when_no_match(self):
        ri = ResourceIntelligenceLayer()
        registry = ModelRegistry()
        registry.register_many([
            ModelMetadata(id="cloud-model", provider="openai", supports_coding=True, cost=0.0, local=False, status=ModelStatus.AVAILABLE),
        ])

        orch = IntelligenceOrchestrator(model_registry=registry)
        orch.set_resource_intelligence(ri)

        intent = ClassifiedIntent(category=IntentCategory.CODING, confidence=0.9, source="test")

        import sentinel.core.resource_intelligence as ri_module
        original = ri_module.ResourceIntelligenceLayer.evaluate

        def mock_evaluate(self, model, state=None):
            return ResourceDecision(allowed=False, reason="simulated rejection", score_modifier=-100)

        ri_module.ResourceIntelligenceLayer.evaluate = mock_evaluate
        try:
            decision = orch.orchestrate(intent)
            assert decision.status == "no_capable_model"
        finally:
            ri_module.ResourceIntelligenceLayer.evaluate = original

    def test_resource_intelligence_affects_scoring(self):
        ri = ResourceIntelligenceLayer()
        registry = ModelRegistry()
        registry.register_many([
            ModelMetadata(id="model-a", provider="local", supports_coding=True, supports_reasoning=True, cost=0.0, local=True, speed="fast", status=ModelStatus.AVAILABLE),
            ModelMetadata(id="model-b", provider="local", supports_coding=True, supports_reasoning=True, cost=0.0, local=True, speed="fast", status=ModelStatus.AVAILABLE),
        ])

        orch = IntelligenceOrchestrator(model_registry=registry)
        orch.set_resource_intelligence(ri)

        import sentinel.core.resource_intelligence as ri_module
        original_eval = ri_module.ResourceIntelligenceLayer.evaluate

        def mock_evaluate(self, model, state=None):
            mod = 20 if model.id == "model-a" else -20
            return ResourceDecision(allowed=True, reason=f"test mod {mod}", score_modifier=mod)

        ri_module.ResourceIntelligenceLayer.evaluate = mock_evaluate
        try:
            intent = ClassifiedIntent(category=IntentCategory.CODING, confidence=0.9, source="test")
            decision = orch.orchestrate(intent)
            assert decision.model_id == "model-a"
            assert "score modifier +20" in decision.reasoning or "Resource: test mod 20" in decision.reasoning
        finally:
            ri_module.ResourceIntelligenceLayer.evaluate = original_eval

    def test_reasoning_includes_resource_info(self):
        ri = ResourceIntelligenceLayer()
        registry = ModelRegistry()
        registry.register_many([
            ModelMetadata(id="test-model", provider="local", supports_coding=True, supports_reasoning=True, cost=0.0, local=True, speed="fast", status=ModelStatus.AVAILABLE),
        ])
        import sentinel.core.resource_intelligence as ri_module
        original = ri_module.ResourceIntelligenceLayer.evaluate

        def mock_evaluate(self, model, state=None):
            return ResourceDecision(allowed=True, reason="test resource bonus", score_modifier=15)

        ri_module.ResourceIntelligenceLayer.evaluate = mock_evaluate
        try:
            orch = IntelligenceOrchestrator(model_registry=registry)
            orch.set_resource_intelligence(ri)
            intent = ClassifiedIntent(category=IntentCategory.CODING, confidence=0.9, source="test")
            decision = orch.orchestrate(intent)
            assert "Resource:" in decision.reasoning or "score modifier" in decision.reasoning
        finally:
            ri_module.ResourceIntelligenceLayer.evaluate = original
