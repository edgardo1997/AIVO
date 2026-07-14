import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch
import pytest

from sentinel.core.model_router import (
    ModelRouter, TaskType, ProviderSpec, RouterDecision,
    FALLBACK_STRATEGIES, ProviderAvailability,
)
from sentinel.core.circuit_breaker import CircuitBreaker


@pytest.fixture(autouse=True)
def all_test_providers_available(monkeypatch):
    monkeypatch.setattr(
        ModelRouter,
        "provider_availability",
        lambda self, provider_id, refresh=False: ProviderAvailability(
            provider_id, True, "test_available", 0.0,
        ),
    )


class TestFallbackChainingUnit:
    def test_default_fallback_strategy(self):
        mr = ModelRouter()
        stats = mr.fallback_stats()
        assert stats["strategy"] == "chain"
        assert stats["max_fallbacks"] == 5
        assert stats["default_chain"] == []

    def test_set_default_fallback_chain(self):
        mr = ModelRouter()
        mr.set_default_fallback_chain(["groq", "ollama"])
        assert mr._default_fallback_chain == ["groq", "ollama"]

    def test_set_fallback_strategy_valid(self):
        mr = ModelRouter()
        mr.set_fallback_strategy("round_robin")
        assert mr._fallback_strategy == "round_robin"

    def test_set_fallback_strategy_invalid(self):
        mr = ModelRouter()
        with pytest.raises(ValueError):
            mr.set_fallback_strategy("invalid")

    def test_set_max_fallbacks(self):
        mr = ModelRouter()
        mr.set_max_fallbacks(3)
        assert mr._max_fallbacks == 3

    def test_set_max_fallbacks_min_one(self):
        mr = ModelRouter()
        mr.set_max_fallbacks(0)
        assert mr._max_fallbacks == 1
        mr.set_max_fallbacks(-5)
        assert mr._max_fallbacks == 1

    def test_build_fallback_chain_uses_provider_chain(self):
        p = ProviderSpec(id="primary", name="Primary", task_types=[TaskType.QUICK],
                         fallback_chain=["groq", "ollama"])
        mr = ModelRouter(providers=[p])
        # register fallback providers as well
        mr._providers["groq"] = ProviderSpec(id="groq", name="Groq", task_types=[TaskType.QUICK])
        mr._providers["ollama"] = ProviderSpec(id="ollama", name="Ollama", task_types=[TaskType.QUICK])
        decision = RouterDecision(provider_id="primary", model="m", task_type=TaskType.QUICK,
                                  strategy="priority", reason="test")
        chain = mr._build_fallback_chain(decision, TaskType.QUICK)
        ids = [c.provider_id for c in chain]
        assert ids == ["primary", "groq", "ollama"]

    def test_build_fallback_chain_uses_global_chain(self):
        mr = ModelRouter()
        mr._providers["groq"] = ProviderSpec(id="groq", name="Groq", task_types=[TaskType.QUICK])
        mr._providers["ollama"] = ProviderSpec(id="ollama", name="Ollama", task_types=[TaskType.QUICK])
        mr.set_default_fallback_chain(["groq", "ollama"])
        decision = RouterDecision(provider_id="primary", model="m", task_type=TaskType.QUICK,
                                  strategy="priority", reason="test")
        chain = mr._build_fallback_chain(decision, TaskType.QUICK)
        ids = [c.provider_id for c in chain]
        assert ids == ["primary", "groq", "ollama"]

    def test_build_fallback_chain_skips_unknown(self):
        mr = ModelRouter()
        mr._providers["ollama"] = ProviderSpec(id="ollama", name="Ollama", task_types=[TaskType.QUICK])
        mr.set_default_fallback_chain(["nonexistent", "ollama"])
        decision = RouterDecision(provider_id="primary", model="m", task_type=TaskType.QUICK,
                                  strategy="priority", reason="test")
        chain = mr._build_fallback_chain(decision, TaskType.QUICK)
        ids = [c.provider_id for c in chain]
        assert ids == ["primary", "ollama"]

    def test_build_fallback_chain_respects_max(self):
        mr = ModelRouter()
        mr._providers["groq"] = ProviderSpec(id="groq", name="Groq", task_types=[TaskType.QUICK])
        mr._providers["ollama"] = ProviderSpec(id="ollama", name="Ollama", task_types=[TaskType.QUICK])
        mr.set_default_fallback_chain(["groq", "ollama"])
        mr.set_max_fallbacks(1)
        decision = RouterDecision(provider_id="primary", model="m", task_type=TaskType.QUICK,
                                  strategy="priority", reason="test")
        chain = mr._build_fallback_chain(decision, TaskType.QUICK)
        ids = [c.provider_id for c in chain]
        assert ids == ["primary", "groq"]
        assert len(ids) == 2

    def test_build_fallback_chain_falls_back_to_select_all(self):
        mr = ModelRouter()
        # primary must be registered; add another local provider so select_all has a candidate
        mr._providers["local_test"] = ProviderSpec(
            id="local_test", name="Local Test", task_types=[TaskType.QUICK],
            is_local=True, requires_key=False,
        )
        decision = RouterDecision(provider_id="ollama", model="m", task_type=TaskType.QUICK,
                                  strategy="priority", reason="test")
        chain = mr._build_fallback_chain(decision, TaskType.QUICK)
        assert chain[0].provider_id == "ollama"
        assert len(chain) > 1

    def test_build_fallback_chain_no_duplicates(self):
        mr = ModelRouter()
        mr._providers["ollama"] = ProviderSpec(id="ollama", name="Ollama", task_types=[TaskType.QUICK])
        mr._providers["groq"] = ProviderSpec(id="groq", name="Groq", task_types=[TaskType.QUICK])
        mr.set_default_fallback_chain(["ollama", "ollama", "groq"])
        decision = RouterDecision(provider_id="primary", model="m", task_type=TaskType.QUICK,
                                  strategy="priority", reason="test")
        chain = mr._build_fallback_chain(decision, TaskType.QUICK)
        ids = [c.provider_id for c in chain]
        assert ids == ["primary", "ollama", "groq"]

    def test_fallback_stats_initial(self):
        mr = ModelRouter()
        stats = mr.fallback_stats()
        assert stats["total_fallbacks"] == 0
        assert stats["fallback_counts"] == {}
        assert stats["recent_history"] == []

    def test_reset_fallback_stats(self):
        mr = ModelRouter()
        mr._fallback_stats["groq"] = 5
        mr._fallback_history.append({"primary": "a", "used": "b"})
        count = mr.reset_fallback_stats()
        assert count == 5
        assert mr._fallback_stats == {}
        assert mr._fallback_history == []

    def test_record_fallback(self):
        mr = ModelRouter()
        mr._record_fallback("groq")
        mr._record_fallback("groq")
        mr._record_fallback("ollama")
        assert mr._fallback_stats["groq"] == 2
        assert mr._fallback_stats["ollama"] == 1

    def test_provider_spec_fallback_chain_field(self):
        p = ProviderSpec(id="test", name="Test", task_types=[TaskType.QUICK],
                         fallback_chain=["a", "b"])
        assert p.fallback_chain == ["a", "b"]

    def test_chat_uses_fallback_chain_override(self):
        mr = ModelRouter()
        original_call = mr._call_provider

        call_order = []
        def tracking_call(decision, provider, messages, model_override=None):
            call_order.append(decision.provider_id)
            if decision.provider_id == "groq":
                return {"response": "ok", "provider": "groq", "model": "m", "usage": None}
            raise ConnectionError("fail")

        mr._call_provider = tracking_call
        result = mr.chat([{"role": "user", "content": "hi"}], task_type=TaskType.QUICK,
                         fallback_chain_override=["ollama", "groq"])
        assert result["provider"] == "groq"
        assert call_order == ["ollama", "groq"]

    def test_chat_fallback_records_stats(self):
        mr = ModelRouter()
        def mock_call(decision, provider, messages, model_override=None):
            if decision.provider_id == "groq":
                return {"response": "ok", "provider": "groq", "model": "m", "usage": None}
            raise ConnectionError("fail")

        mr._call_provider = mock_call
        mr.chat([{"role": "user", "content": "hi"}], task_type=TaskType.QUICK,
                fallback_chain_override=["ollama", "groq"])
        stats = mr.fallback_stats()
        assert stats["total_fallbacks"] == 1
        assert "groq" in stats["fallback_counts"]

    def test_fallback_strategies_list(self):
        assert "chain" in FALLBACK_STRATEGIES
        assert "round_robin" in FALLBACK_STRATEGIES
        assert "broadcast" in FALLBACK_STRATEGIES


class TestFallbackIntegration:
    def test_chat_with_circuit_breaker_skips_fallback(self):
        mr = ModelRouter()
        mr._circuit_breaker.record_failure("ollama")
        mr._circuit_breaker.record_failure("ollama")
        mr._circuit_breaker.record_failure("ollama")

        call_log = []
        def mock_call(decision, provider, messages, model_override=None):
            call_log.append(decision.provider_id)
            if decision.provider_id == "groq":
                return {"response": "ok", "provider": "groq", "model": "m", "usage": None}
            raise ConnectionError("fail")

        mr._call_provider = mock_call
        result = mr.chat([{"role": "user", "content": "hi"}], task_type=TaskType.QUICK,
                         fallback_chain_override=["ollama", "groq", "openrouter"])
        # ollama should be skipped (circuit open), groq should succeed
        assert "ollama" not in call_log
        assert result["provider"] == "groq"

    def test_all_fallbacks_open_raises_error(self):
        mr = ModelRouter()
        for pid in ["ollama", "groq"]:
            mr._circuit_breaker.record_failure(pid)
            mr._circuit_breaker.record_failure(pid)
            mr._circuit_breaker.record_failure(pid)

        def mock_call(decision, provider, messages, model_override=None):
            raise ConnectionError("fail")

        mr._call_provider = mock_call
        with pytest.raises(RuntimeError) as exc:
            mr.chat([{"role": "user", "content": "hi"}], task_type=TaskType.QUICK,
                    fallback_chain_override=["ollama", "groq"])
        assert "circuit breaker open" in str(exc.value).lower()

    def test_primary_succeeds_no_fallback_recorded(self):
        mr = ModelRouter()
        def mock_call(decision, provider, messages, model_override=None):
            return {"response": "ok", "provider": decision.provider_id, "model": "m", "usage": None}

        mr._call_provider = mock_call
        result = mr.chat([{"role": "user", "content": "hi"}], task_type=TaskType.QUICK)
        stats = mr.fallback_stats()
        assert stats["total_fallbacks"] == 0

    def test_router_constructor_accepts_fallback_params(self):
        mr = ModelRouter(default_fallback_chain=["groq", "ollama"], fallback_strategy="round_robin", max_fallbacks=3)
        assert mr._default_fallback_chain == ["groq", "ollama"]
        assert mr._fallback_strategy == "round_robin"
        assert mr._max_fallbacks == 3


class TestFallbackAPI:
    def setup_method(self):
        from modules.sentinel_bridge import reset_bridge
        reset_bridge()

    def test_get_fallback_stats_endpoint(self):
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        resp = client.get("/api/sentinel/fallback/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "enabled" in data

    def test_reset_fallback_stats_endpoint(self):
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        resp = client.post("/api/sentinel/fallback/reset-stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "reset" in data
