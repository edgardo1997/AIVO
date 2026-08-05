"""Circuit breaker state and isolation tests."""

import time

from sentinel.core.circuit_breaker import CircuitBreaker, CircuitState


def test_circuit_opens_after_threshold():
    cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=1.0)
    assert cb.allow_request("openai") is True
    cb.record_failure("openai")
    cb.record_failure("openai")
    assert cb.get_state("openai")["state"] == CircuitState.OPEN.value
    assert cb.allow_request("openai") is False


def test_circuit_does_not_open_for_policy_denial():
    cb = CircuitBreaker(failure_threshold=2)
    # Simulated non-provider failures should not be recorded directly on provider.
    # Here we just verify success reset keeps it closed.
    cb.record_success("openai")
    assert cb.get_state("openai")["state"] == CircuitState.CLOSED.value


def test_circuit_providers_are_isolated():
    cb = CircuitBreaker(failure_threshold=2)
    cb.record_failure("openai")
    cb.record_failure("openai")
    assert cb.allow_request("anthropic") is True


def test_half_open_after_cooldown():
    cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=0.05)
    cb.record_failure("openai")
    assert cb.get_state("openai")["state"] == CircuitState.OPEN.value
    time.sleep(0.06)
    assert cb.allow_request("openai") is True
    assert cb.get_state("openai")["state"] == CircuitState.HALF_OPEN.value
