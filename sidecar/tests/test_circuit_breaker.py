import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch
import time
import pytest

from sentinel.core.circuit_breaker import CircuitBreaker, CircuitState
from sentinel.core.model_router import ModelRouter, TaskType, ProviderSpec


class TestCircuitBreakerUnit:
    def test_initial_state_is_closed(self):
        cb = CircuitBreaker()
        state = cb.get_state("openrouter")
        assert state["state"] == "closed"
        assert state["consecutive_failures"] == 0

    def test_allow_request_when_closed(self):
        cb = CircuitBreaker()
        assert cb.allow_request("openrouter") is True

    def test_failure_threshold_opens_circuit(self):
        cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=10)
        cb.record_failure("openrouter")
        assert cb.allow_request("openrouter") is True
        cb.record_failure("openrouter")
        assert cb.allow_request("openrouter") is False
        state = cb.get_state("openrouter")
        assert state["state"] == "open"
        assert state["consecutive_failures"] == 2

    def test_success_resets_failures(self):
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure("openrouter")
        cb.record_success("openrouter")
        assert cb.allow_request("openrouter") is True
        state = cb.get_state("openrouter")
        assert state["consecutive_failures"] == 0
        assert state["state"] == "closed"

    def test_half_open_after_cooldown(self):
        cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=0.05)
        cb.record_failure("openrouter")
        assert cb.allow_request("openrouter") is False
        time.sleep(0.06)
        assert cb.allow_request("openrouter") is True
        state = cb.get_state("openrouter")
        assert state["state"] == "half_open"
        assert state["probe_in_flight"] is True

    def test_half_open_allows_only_one_probe(self):
        cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=0.01)
        cb.record_failure("openrouter")
        time.sleep(0.02)
        assert cb.allow_request("openrouter") is True
        assert cb.allow_request("openrouter") is False

    def test_half_open_success_closes(self):
        cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=0.05)
        cb.record_failure("openrouter")
        time.sleep(0.06)
        assert cb.allow_request("openrouter") is True
        cb.record_success("openrouter")
        state = cb.get_state("openrouter")
        assert state["state"] == "closed"

    def test_half_open_failure_reopens(self):
        cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=0.05)
        cb.record_failure("openrouter")
        time.sleep(0.06)
        assert cb.allow_request("openrouter") is True
        cb.record_failure("openrouter")
        state = cb.get_state("openrouter")
        assert state["state"] == "open"

    def test_reset_provider(self):
        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure("openrouter")
        cb.record_failure("ollama")
        assert cb.reset(provider_id="openrouter") == 1
        assert cb.allow_request("openrouter") is True
        assert cb.allow_request("ollama") is False

    def test_reset_all(self):
        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure("openrouter")
        cb.record_failure("ollama")
        assert cb.reset() == 2
        assert cb.allow_request("openrouter") is True
        assert cb.allow_request("ollama") is True

    def test_get_all_states(self):
        cb = CircuitBreaker()
        cb.record_failure("openrouter")
        cb.record_failure("openrouter")
        cb.record_failure("openrouter")
        cb.record_failure("groq")
        cb.record_failure("groq")
        states = cb.get_all_states()
        assert len(states) == 2
        assert states[0]["provider_id"] == "groq"
        assert states[1]["provider_id"] == "openrouter"

    def test_remaining_cooldown(self):
        cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=10)
        cb.record_failure("openrouter")
        state = cb.get_state("openrouter")
        assert state["remaining_cooldown"] > 9.0


class TestCircuitBreakerIntegration:
    def test_router_skips_open_provider(self):
        mr = ModelRouter()
        mr._circuit_breaker.record_failure("openrouter")
        mr._circuit_breaker.record_failure("openrouter")
        mr._circuit_breaker.record_failure("openrouter")
        # openrouter now open, should fall through to other providers
        # but with no keys configured, all will fail
        with pytest.raises(RuntimeError):
            mr.chat([{"role": "user", "content": "hi"}], task_type=TaskType.QUICK)

    def test_router_records_success_on_success(self):
        mr = ModelRouter()
        # patch _call_provider to succeed
        original = mr._call_provider

        def mock_call(decision, provider, messages, model_override=None):
            return {"response": "ok", "provider": decision.provider_id, "model": decision.model, "usage": None}

        mr._call_provider = mock_call
        result = mr.chat([{"role": "user", "content": "hi"}], task_type=TaskType.QUICK)
        assert result["response"] == "ok"
        state = mr._circuit_breaker.get_state("openrouter")
        assert state["state"] == "closed"

    def test_router_records_failure_on_exception(self):
        mr = ModelRouter()
        mr._circuit_breaker = CircuitBreaker(failure_threshold=1)
        def mock_call(decision, provider, messages, model_override=None):
            raise ConnectionError("API unavailable")

        mr._call_provider = mock_call
        with pytest.raises(RuntimeError):
            mr.chat([{"role": "user", "content": "hi"}], task_type=TaskType.QUICK)
        # the first candidate selected (ollama, since it has no key requirement)
        # should be recorded as failed and circuit opened
        state = mr._circuit_breaker.get_state("ollama")
        assert state["consecutive_failures"] == 1
        assert state["state"] == "open"

    def test_all_open_raises_helpful_error(self):
        mr = ModelRouter()
        # open all providers
        for pid in list(mr._providers.keys()):
            mr._circuit_breaker.record_failure(pid)
            mr._circuit_breaker.record_failure(pid)
            mr._circuit_breaker.record_failure(pid)

        with pytest.raises(RuntimeError) as exc:
            mr.chat([{"role": "user", "content": "hi"}], task_type=TaskType.QUICK)
        assert "circuit breaker open" in str(exc.value).lower()


class TestCircuitBreakerAPI:
    def setup_method(self):
        from modules.sentinel_bridge import reset_bridge
        reset_bridge()

    def test_get_circuits_empty(self):
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        resp = client.get("/api/sentinel/circuit-breaker")
        assert resp.status_code == 200
        data = resp.json()
        assert "model_circuits" in data
        assert "tool_circuits" in data

    def test_reset_circuits(self):
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        resp = client.post("/api/sentinel/circuit-breaker/reset")
        assert resp.status_code == 200
        data = resp.json()
        assert "reset" in data
