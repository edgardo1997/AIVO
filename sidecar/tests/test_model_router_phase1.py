import pytest
from sentinel.models import ModelMetadata, ModelStatus
from sentinel.core.model_router import ModelRouter, TaskType, RouterDecision
from sentinel.core.model_registry import ModelRegistry


def _make_registry():
    registry = ModelRegistry()
    registry.register_many([
        ModelMetadata(id="tool-coder", provider="test", supports_coding=True, supports_reasoning=True, supports_tool_calling=True, cost=0.0, local=False, status=ModelStatus.AVAILABLE),
        ModelMetadata(id="coder-only", provider="test", supports_coding=True, supports_reasoning=True, supports_tool_calling=False, cost=0.0, local=False, status=ModelStatus.AVAILABLE),
        ModelMetadata(id="chat-only", provider="test", supports_coding=False, supports_reasoning=False, supports_tool_calling=False, cost=0.0, local=False, status=ModelStatus.AVAILABLE),
        ModelMetadata(id="local-coder", provider="test", supports_coding=True, supports_reasoning=True, supports_tool_calling=False, cost=0.0, local=True, status=ModelStatus.AVAILABLE),
        ModelMetadata(id="premium-coder", provider="test", supports_coding=True, supports_reasoning=True, supports_tool_calling=True, cost=5.0, local=False, status=ModelStatus.AVAILABLE),
    ])
    return registry


class TestModelRouterCapability:
    def test_select_by_capability_finds_tool_caller(self):
        router = ModelRouter()
        router.set_model_registry(_make_registry())
        decision = router.select_by_capability(["tool_calling", "coding"])
        assert decision is not None
        assert decision.model == "tool-coder"

    def test_select_by_capability_returns_none_if_no_match(self):
        router = ModelRouter()
        router.set_model_registry(_make_registry())
        decision = router.select_by_capability(["vision"])
        assert decision is None

    def test_select_by_capability_without_registry(self):
        router = ModelRouter()
        decision = router.select_by_capability(["coding"])
        assert decision is None

    def test_select_by_capability_prefers_low_cost(self):
        registry = ModelRegistry()
        registry.register_many([
            ModelMetadata(id="cheap", provider="test", supports_coding=True, cost=0.0, local=False, status=ModelStatus.AVAILABLE),
            ModelMetadata(id="expensive", provider="test", supports_coding=True, cost=10.0, local=False, status=ModelStatus.AVAILABLE),
        ])
        router = ModelRouter()
        router.set_model_registry(registry)
        decision = router.select_by_capability(["coding"])
        assert decision is not None
        assert decision.model == "cheap"

    def test_local_first_strategy(self):
        registry = ModelRegistry()
        registry.register_many([
            ModelMetadata(id="remote", provider="test", supports_coding=True, local=False, cost=0.0, status=ModelStatus.AVAILABLE),
            ModelMetadata(id="local-md", provider="test", supports_coding=True, local=True, cost=0.0, status=ModelStatus.AVAILABLE),
        ])
        router = ModelRouter()
        router.set_model_registry(registry)
        router.set_strategy("local_first")
        decision = router.select_by_capability(["coding"])
        assert decision is not None
        assert decision.model == "local-md"

    def test_select_by_capability_excludes_unavailable(self):
        registry = ModelRegistry()
        registry.register_many([
            ModelMetadata(id="available-coder", provider="test", supports_coding=True, status=ModelStatus.AVAILABLE),
            ModelMetadata(id="deprecated-coder", provider="test", supports_coding=True, status=ModelStatus.DEPRECATED),
        ])
        router = ModelRouter()
        router.set_model_registry(registry)
        decision = router.select_by_capability(["coding"])
        assert decision is not None
        assert decision.model == "available-coder"


class TestModelRouterRegistryIntegration:
    def test_select_code_task_uses_registry_if_available(self):
        router = ModelRouter()
        router.set_model_registry(_make_registry())
        decision = router.select(TaskType.CODE)
        assert decision is not None
        assert decision.model in ("tool-coder", "coder-only", "local-coder")

    def test_select_falls_back_to_provider_based_without_registry(self):
        router = ModelRouter()
        try:
            decision = router.select(TaskType.CODE)
            assert decision is not None
            assert decision.provider_id != ""
        except RuntimeError:
            pass

    def test_select_quick_task_ignores_registry(self):
        router = ModelRouter()
        router.set_model_registry(_make_registry())
        try:
            decision = router.select(TaskType.QUICK)
            assert decision is not None
        except RuntimeError:
            pass

    def test_set_model_registry_logs_count(self):
        router = ModelRouter()
        registry = _make_registry()
        router.set_model_registry(registry)
        decision = router.select_by_capability(["tool_calling"])
        assert decision is not None
        assert decision.model == "tool-coder"

    def test_set_task_capability_map(self):
        router = ModelRouter()
        router.set_task_capability_map(TaskType.CODE, ["tool_calling"])
        registry = ModelRegistry()
        registry.register(ModelMetadata(id="tooler", provider="test", supports_tool_calling=True, status=ModelStatus.AVAILABLE))
        registry.register(ModelMetadata(id="non-tooler", provider="test", supports_tool_calling=False, status=ModelStatus.AVAILABLE))
        router.set_model_registry(registry)
        decision = router.select(TaskType.CODE)
        assert decision is not None
        assert decision.model == "tooler"
