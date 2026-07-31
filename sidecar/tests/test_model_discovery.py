import pytest
from sentinel.core.model_discovery import (
    ModelDiscovery,
    DiscoveredModel,
    OllamaDiscovery,
    LMStudioDiscovery,
    CloudProviderDiscovery,
    MODEL_CAPABILITY_HINTS,
    CONTEXT_WINDOW_HINTS,
    SPEED_HINTS,
)


class FakeRegistry:
    def __init__(self):
        self._models = {}

    def register(self, m):
        if m.id in self._models:
            raise ValueError(f"Duplicate {m.id}")
        self._models[m.id] = m

    def get(self, mid):
        return self._models.get(mid)

    def list_all(self):
        return list(self._models.values())

    def count(self):
        return len(self._models)


class TestDiscoveredModel:
    def test_defaults(self):
        dm = DiscoveredModel()
        assert dm.model_id == ""
        assert dm.local is False
        assert dm.supports_coding is False
        assert dm.supports_reasoning is False

    def test_to_metadata(self):
        dm = DiscoveredModel(
            model_id="qwen3:8b",
            provider="ollama",
            local=True,
            supports_coding=True,
            supports_reasoning=True,
            context_window=32768,
            speed="fast",
        )
        meta = dm.to_metadata()
        assert meta.id == "qwen3:8b"
        assert meta.provider == "ollama"
        assert meta.local is True
        assert meta.supports_coding is True
        assert meta.supports_reasoning is True
        assert meta.context_window == 32768

    def test_unknown_capabilities_default_false(self):
        """Test 6: Unknown models don't get fake capabilities."""
        dm = DiscoveredModel(model_id="completely-unknown-model", provider="ollama", local=True)
        meta = dm.to_metadata()
        assert meta.supports_coding is False
        assert meta.supports_reasoning is False
        assert meta.supports_tool_calling is False
        assert meta.supports_vision is False


class TestOllamaDiscovery:
    def test_build_discovered_known_model(self):
        d = OllamaDiscovery()
        dm = d._build_discovered("qwen3:8b")
        assert dm.provider == "ollama"
        assert dm.local is True
        assert dm.supports_coding is True
        assert dm.supports_reasoning is True

    def test_build_discovered_unknown_model(self):
        d = OllamaDiscovery()
        dm = d._build_discovered("some-random-model:latest")
        assert dm.supports_coding is False
        assert dm.supports_reasoning is False
        assert dm.speed == "unknown"

    def test_build_discovered_speed(self):
        d = OllamaDiscovery()
        dm = d._build_discovered("llama3:70b")
        assert dm.speed == "slow"

    def test_discover_models_no_server(self):
        d = OllamaDiscovery(base_url="http://localhost:1")
        models = d.discover_models()
        assert models == []

    def test_hint_resolution_longest_key_wins(self):
        d = OllamaDiscovery()
        dm = d._build_discovered("qwen3:8b")
        assert dm.supports_coding is True
        assert dm.supports_reasoning is True


class TestLMStudioDiscovery:
    def test_build_discovered_known_model(self):
        d = LMStudioDiscovery()
        dm = d._build_discovered("llama3.1:8b")
        assert dm.provider == "lmstudio"
        assert dm.local is True
        assert dm.supports_coding is True

    def test_build_discovered_unknown(self):
        d = LMStudioDiscovery()
        dm = d._build_discovered("custom-model")
        assert dm.supports_coding is False

    def test_discover_no_server(self):
        d = LMStudioDiscovery(base_url="http://localhost:1")
        models = d.discover_models()
        assert models == []

    def test_context_window_hint(self):
        d = LMStudioDiscovery()
        dm = d._build_discovered("llama3.3:70b")
        assert dm.context_window == 131072


class TestCloudProviderDiscovery:
    def test_no_api_key_returns_empty(self):
        d = CloudProviderDiscovery("openai", "https://api.openai.com/v1", api_key="")
        models = d.discover_models()
        assert models == []

    def test_build_discovered_known(self):
        d = CloudProviderDiscovery("openai", "https://api.openai.com/v1", api_key="sk-test")
        dm = d._build_discovered("gpt-4o")
        assert dm.provider == "openai"
        assert dm.local is False
        assert dm.supports_coding is True
        assert dm.supports_reasoning is True

    def test_build_discovered_unknown(self):
        d = CloudProviderDiscovery("anthropic", "https://api.anthropic.com/v1", api_key="sk-test")
        dm = d._build_discovered("claude-4-unknown-model")
        assert dm.supports_coding is True
        assert dm.supports_reasoning is True

    def test_discover_no_server(self):
        d = CloudProviderDiscovery("openai", "http://localhost:1", api_key="sk-test")
        models = d.discover_models()
        assert models == []

    def test_discover_no_key_does_not_call_api(self):
        d = CloudProviderDiscovery("openai", "http://localhost:1", api_key="")
        models = d.discover_models()
        assert models == []

    def test_fast_speed_for_cloud(self):
        d = CloudProviderDiscovery("openai", "https://api.openai.com/v1", api_key="sk-test")
        dm = d._build_discovered("gpt-4o")
        assert dm.speed == "fast"

    def test_tags_include_provider(self):
        d = CloudProviderDiscovery("mistral", "https://api.mistral.ai/v1", api_key="sk-test")
        dm = d._build_discovered("mistral-large")
        assert "mistral" in dm.tags


class TestModelCapabilityHints:
    def test_known_hints_exist(self):
        assert "gpt-4o" in MODEL_CAPABILITY_HINTS
        assert "claude" in MODEL_CAPABILITY_HINTS
        assert "gemini" in MODEL_CAPABILITY_HINTS
        assert "llama3" in MODEL_CAPABILITY_HINTS
        assert "qwen3" in MODEL_CAPABILITY_HINTS
        assert "deepseek" in MODEL_CAPABILITY_HINTS

    def test_embeddings_hints(self):
        assert "nomic-embed" in MODEL_CAPABILITY_HINTS
        assert MODEL_CAPABILITY_HINTS["nomic-embed"]["supports_embeddings"] is True

    def test_context_window_hints(self):
        assert "llama3.3" in CONTEXT_WINDOW_HINTS
        assert "qwen3:8b" in CONTEXT_WINDOW_HINTS

    def test_speed_hints(self):
        assert SPEED_HINTS.get("7b") == "fast"
        assert SPEED_HINTS.get("70b") == "slow"


class FakeOllamaDiscoverer:
    _provider_id = "ollama"

    def __init__(self, models=None):
        self._models = models or ["qwen3:8b", "llama3:70b"]

    def discover_models(self):
        return [
            DiscoveredModel(
                model_id=m, provider="ollama", local=True,
                supports_coding="qwen" in m or "llama" in m,
                supports_reasoning="qwen" in m or "llama" in m,
            )
            for m in self._models
        ]


class FakeCloudDiscoverer:
    _provider_id = "openai"

    def __init__(self, models=None):
        self._models = models or ["gpt-4o", "gpt-4o-mini"]

    def discover_models(self):
        return [
            DiscoveredModel(
                model_id=m, provider="openai", local=False,
                supports_coding=True, supports_reasoning=True,
            )
            for m in self._models
        ]


class TestModelDiscovery:
    def test_discover_all(self):
        discovery = ModelDiscovery()
        discovery.add_discoverer(FakeOllamaDiscoverer())
        results = discovery.discover_all()
        assert "ollama" in results
        assert len(results["ollama"]) == 2

    def test_sync_registry_adds_new_models(self):
        registry = FakeRegistry()
        discovery = ModelDiscovery(model_registry=registry)
        discovery.add_discoverer(FakeOllamaDiscoverer())
        result = discovery.run_full_discovery()
        assert result["status"] == "success"
        assert result["added"] == 2
        assert registry.get("qwen3:8b") is not None
        assert registry.get("llama3:70b") is not None

    def test_sync_registry_detects_new_model_appears(self):
        """Test 4: New model appears and is detected."""
        registry = FakeRegistry()
        discovery = ModelDiscovery(model_registry=registry)
        discovery.add_discoverer(FakeOllamaDiscoverer(models=["qwen3:8b"]))
        discovery.run_full_discovery()
        assert registry.get("qwen3:8b") is not None
        assert registry.count() == 1

        discovery2 = ModelDiscovery(model_registry=registry)
        discovery2.add_discoverer(FakeOllamaDiscoverer(models=["qwen3:8b", "deepseek-coder"]))
        discovery2.run_full_discovery()
        assert registry.get("deepseek-coder") is not None
        assert registry.get("qwen3:8b") is not None

    def test_no_registry_returns_warning(self):
        discovery = ModelDiscovery()
        result = discovery.sync_registry()
        assert result["status"] == "no_registry"

    def test_multiple_providers(self):
        registry = FakeRegistry()
        discovery = ModelDiscovery(model_registry=registry)
        discovery.add_discoverer(FakeOllamaDiscoverer())
        discovery.add_discoverer(FakeCloudDiscoverer())
        result = discovery.run_full_discovery()
        assert result["total_after"] == 4

    def test_get_discovered_models(self):
        discovery = ModelDiscovery()
        discovery.add_discoverer(FakeOllamaDiscoverer())
        discovery.discover_all()
        result = discovery.get_discovered_models()
        assert "ollama" in result

    def test_get_discoverers(self):
        d = FakeOllamaDiscoverer()
        discovery = ModelDiscovery()
        discovery.add_discoverer(d)
        assert d in discovery.get_discoverers()

    def test_discoverer_error_does_not_crash(self):
        discovery = ModelDiscovery()

        class BrokenDiscoverer:
            def discover_models(self):
                raise RuntimeError("API failure")

        discovery.add_discoverer(BrokenDiscoverer())
        discovery.add_discoverer(FakeOllamaDiscoverer())
        results = discovery.discover_all()
        assert "BrokenDiscoverer" in results
        assert results["BrokenDiscoverer"] == []
        assert "ollama" in results
        assert len(results["ollama"]) == 2

    def test_cloud_discovery_no_key(self):
        d = CloudProviderDiscovery("openai", "https://api.openai.com/v1", api_key="")
        models = d.discover_models()
        assert models == []

    def test_ollama_no_server_returns_empty(self):
        d = OllamaDiscovery(base_url="http://localhost:1")
        models = d.discover_models()
        assert models == []

    def test_lmstudio_no_server_returns_empty(self):
        d = LMStudioDiscovery(base_url="http://localhost:1")
        models = d.discover_models()
        assert models == []

    def test_sync_with_existing_models(self):
        registry = FakeRegistry()
        discovery = ModelDiscovery(model_registry=registry)
        discovery.add_discoverer(FakeOllamaDiscoverer(models=["qwen3:8b"]))
        discovery.run_full_discovery()
        first_count = registry.count()

        discovery2 = ModelDiscovery(model_registry=registry)
        discovery2.add_discoverer(FakeOllamaDiscoverer(models=["qwen3:8b"]))
        discovery2.run_full_discovery()
        assert registry.count() == first_count

    def test_add_discoverer_appends(self):
        discovery = ModelDiscovery()
        assert len(discovery.get_discoverers()) == 0
        discovery.add_discoverer(FakeOllamaDiscoverer())
        assert len(discovery.get_discoverers()) == 1
