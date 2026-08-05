"""ProviderRegistry canonical responsibility tests."""

import pytest
from sentinel.core.provider_registry import ProviderRegistry


def test_registry_lists_builtin_providers():
    reg = ProviderRegistry()
    pids = [p.id for p in reg.list_providers()]
    assert "sentinel_local" in pids
    assert "openai" in pids


def test_registry_get_provider():
    reg = ProviderRegistry()
    spec = reg.get_provider("openai")
    assert spec is not None
    assert not spec.is_local


def test_registry_list_models_for_provider():
    reg = ProviderRegistry()
    models = reg.list_models("openai")
    assert len(models) >= 1
    assert all(not m.is_local and m.is_cloud for m in models)


def test_registry_resolve_unknown_returns_none():
    reg = ProviderRegistry()
    assert reg.resolve_model("missing", "x") is None
