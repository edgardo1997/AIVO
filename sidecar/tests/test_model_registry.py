import pytest
from sentinel.models import ModelMetadata, ModelStatus
from sentinel.core.model_registry import ModelRegistry, TASK_CAPABILITY_MAP


class TestModelMetadata:
    def test_create_valid(self):
        m = ModelMetadata(id="test-model", provider="test-provider", context_window=8192)
        assert m.id == "test-model"
        assert m.provider == "test-provider"
        assert m.context_window == 8192
        assert m.supports_tool_calling is False
        assert m.is_available is True

    def test_create_with_capabilities(self):
        m = ModelMetadata(
            id="coder",
            provider="test",
            supports_coding=True,
            supports_reasoning=True,
            supports_tool_calling=True,
            local=True,
            status=ModelStatus.AVAILABLE,
        )
        assert m.has_capability("coding") is True
        assert m.has_capability("reasoning") is True
        assert m.has_capability("tool_calling") is True
        assert m.has_capability("local") is True
        assert m.has_capability("vision") is False

    def test_invalid_empty_id(self):
        with pytest.raises(ValueError, match="'id' must be a non-empty string"):
            ModelMetadata(id="", provider="test")

    def test_invalid_empty_provider(self):
        with pytest.raises(ValueError, match="'provider' must be a non-empty string"):
            ModelMetadata(id="test", provider="")

    def test_invalid_context_window(self):
        with pytest.raises(ValueError, match="context_window.*>= 1"):
            ModelMetadata(id="test", provider="test", context_window=0)

    def test_invalid_negative_cost(self):
        with pytest.raises(ValueError, match="cost.*>= 0"):
            ModelMetadata(id="test", provider="test", cost=-1.0)

    def test_unavailable_status(self):
        m = ModelMetadata(id="down", provider="test", status=ModelStatus.UNAVAILABLE)
        assert m.is_available is False

    def test_display_name(self):
        m = ModelMetadata(id="my-model", provider="my-provider")
        assert m.display_name == "my-provider/my-model"

    def test_frozen_dataclass(self):
        m = ModelMetadata(id="frozen", provider="test")
        with pytest.raises(Exception):
            m.id = "changed"

    def test_has_capability_unknown_returns_true(self):
        m = ModelMetadata(id="test", provider="test")
        assert m.has_capability("system_access") is True
        assert m.has_capability("risk_analysis") is True


class TestModelRegistry:
    def test_register_and_get(self):
        registry = ModelRegistry()
        m = ModelMetadata(id="alpha", provider="test")
        registry.register(m)
        assert registry.get("alpha") is m

    def test_register_duplicate_raises(self):
        registry = ModelRegistry()
        m = ModelMetadata(id="dup", provider="test")
        registry.register(m)
        with pytest.raises(ValueError, match="already registered"):
            registry.register(ModelMetadata(id="dup", provider="test"))

    def test_register_invalid_type_raises(self):
        registry = ModelRegistry()
        with pytest.raises(TypeError, match="Expected ModelMetadata"):
            registry.register("not-a-model")  # type: ignore

    def test_get_nonexistent(self):
        registry = ModelRegistry()
        assert registry.get("nonexistent") is None

    def test_register_many(self):
        registry = ModelRegistry()
        models = [
            ModelMetadata(id="a", provider="test"),
            ModelMetadata(id="b", provider="test"),
            ModelMetadata(id="c", provider="test"),
        ]
        registry.register_many(models)
        assert registry.count() == 3

    def test_list_all(self):
        registry = ModelRegistry()
        registry.register(ModelMetadata(id="x", provider="test"))
        registry.register(ModelMetadata(id="y", provider="test"))
        all_models = registry.list_all()
        assert len(all_models) == 2
        assert {m.id for m in all_models} == {"x", "y"}

    def test_list_available(self):
        registry = ModelRegistry()
        registry.register(ModelMetadata(id="a1", provider="test", status=ModelStatus.AVAILABLE))
        registry.register(ModelMetadata(id="d1", provider="test", status=ModelStatus.DEPRECATED))
        registry.register(ModelMetadata(id="u1", provider="test", status=ModelStatus.UNAVAILABLE))
        available = registry.list_available()
        assert [m.id for m in available] == ["a1"]

    def test_unregister(self):
        registry = ModelRegistry()
        registry.register(ModelMetadata(id="rm", provider="test"))
        registry.unregister("rm")
        assert registry.get("rm") is None

    def test_unregister_nonexistent_raises(self):
        registry = ModelRegistry()
        with pytest.raises(KeyError):
            registry.unregister("ghost")

    def test_find_by_capability(self):
        registry = ModelRegistry()
        registry.register(ModelMetadata(id="smart", provider="test", supports_coding=True, supports_reasoning=True))
        registry.register(ModelMetadata(id="dumb", provider="test"))
        registry.register(ModelMetadata(id="visionary", provider="test", supports_vision=True))
        coders = registry.find_by_capability("coding")
        assert [m.id for m in coders] == ["smart"]
        vision = registry.find_by_capability("vision")
        assert [m.id for m in vision] == ["visionary"]

    def test_find_by_provider(self):
        registry = ModelRegistry()
        registry.register(ModelMetadata(id="m1", provider="p1"))
        registry.register(ModelMetadata(id="m2", provider="p1"))
        registry.register(ModelMetadata(id="m3", provider="p2"))
        assert len(registry.find_by_provider("p1")) == 2
        assert len(registry.find_by_provider("p2")) == 1
        assert len(registry.find_by_provider("p3")) == 0

    def test_find_candidates_no_capabilities(self):
        registry = ModelRegistry()
        registry.register(ModelMetadata(id="a", provider="test"))
        registry.register(ModelMetadata(id="b", provider="test"))
        assert len(registry.find_candidates([])) == 2

    def test_find_candidates_with_capabilities(self):
        registry = ModelRegistry()
        registry.register(ModelMetadata(id="full", provider="test", supports_coding=True, supports_reasoning=True))
        registry.register(ModelMetadata(id="partial", provider="test", supports_coding=True))
        registry.register(ModelMetadata(id="none", provider="test"))
        candidates = registry.find_candidates(["coding", "reasoning"])
        assert [m.id for m in candidates] == ["full"]

    def test_find_candidates_excludes_unavailable(self):
        registry = ModelRegistry()
        registry.register(ModelMetadata(id="good", provider="test", supports_coding=True, status=ModelStatus.AVAILABLE))
        registry.register(ModelMetadata(id="bad", provider="test", supports_coding=True, status=ModelStatus.UNAVAILABLE))
        candidates = registry.find_candidates(["coding"])
        assert [m.id for m in candidates] == ["good"]

    def test_clear(self):
        registry = ModelRegistry()
        registry.register(ModelMetadata(id="a", provider="test"))
        registry.register(ModelMetadata(id="b", provider="test"))
        registry.clear()
        assert registry.count() == 0

    def test_count(self):
        registry = ModelRegistry()
        assert registry.count() == 0
        registry.register(ModelMetadata(id="n1", provider="test"))
        assert registry.count() == 1


class TestTaskCapabilityMap:
    def test_coding_requires_reasoning(self):
        assert "coding" in TASK_CAPABILITY_MAP["coding"]
        assert "reasoning" in TASK_CAPABILITY_MAP["coding"]

    def test_action_requires_tool_calling(self):
        assert "tool_calling" in TASK_CAPABILITY_MAP["action"]

    def test_chat_has_no_requirements(self):
        assert TASK_CAPABILITY_MAP["chat"] == []

    def test_local_requires_local(self):
        assert "local" in TASK_CAPABILITY_MAP["local"]
