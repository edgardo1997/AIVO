"""Fallback revalidation tests."""

import pytest

from sentinel.core.budget import BudgetManager
from sentinel.core.circuit_breaker import CircuitBreaker
from sentinel.core.fallback_validator import FallbackValidator
from sentinel.core.model_schemas import CapabilityStatus, ModelCandidate, ModelCapability, ModelRequest, ProviderState
from sentinel.core.model_errors import RoutingError, RoutingErrorCode
from sentinel.providers.provider_manager import ProviderManager


def _validator():
    pm = ProviderManager()
    bm = BudgetManager({"openai:gpt-4o": 1.0})
    cb = CircuitBreaker()
    return FallbackValidator(pm, bm, cb)


def _local_candidate():
    return ModelCandidate(
        provider_id="ollama",
        model_id="llama3",
        is_local=True,
        capabilities=[ModelCapability(name="chat", status=CapabilityStatus.DECLARED)],
        healthy=True,
    )


def _cloud_candidate():
    return ModelCandidate(
        provider_id="openai",
        model_id="gpt-4o",
        is_local=False,
        is_cloud=True,
        capabilities=[ModelCapability(name="chat", status=CapabilityStatus.DECLARED)],
        healthy=True,
    )


def test_local_only_rejects_cloud():
    v = _validator()
    req = ModelRequest(task_type="chat", local_only=True)
    with pytest.raises(RoutingError) as exc:
        v.revalidate(req, _cloud_candidate(), [], 100)
    assert exc.value.code == RoutingErrorCode.MODEL_CLOUD_NOT_AUTHORIZED


def test_cloud_requires_authority():
    from sentinel.security.cloud_authority import CloudAuthority
    pm = ProviderManager(cloud_authority=CloudAuthority())
    bm = BudgetManager({"openai:gpt-4o": 1.0})
    cb = CircuitBreaker()
    v = FallbackValidator(pm, bm, cb)
    req = ModelRequest(task_type="chat", cloud_allowed=True)
    with pytest.raises(RoutingError) as exc:
        v.revalidate(req, _cloud_candidate(), [], 100)
    assert exc.value.code == RoutingErrorCode.MODEL_CLOUD_NOT_AUTHORIZED


def test_unhealthy_provider_rejected():
    v = _validator()
    c = _cloud_candidate()
    c.healthy = False
    req = ModelRequest(task_type="chat", cloud_allowed=True)
    with pytest.raises(RoutingError) as exc:
        v.revalidate(req, c, [], 100)
    assert exc.value.code == RoutingErrorCode.PROVIDER_UNAVAILABLE


def test_local_validated():
    v = _validator()
    req = ModelRequest(task_type="chat", local_only=True)
    dec = v.revalidate(req, _local_candidate(), [], 100)
    assert dec.selected_provider == "ollama"
