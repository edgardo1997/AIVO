"""ProviderManager canonical contract tests."""

from sentinel.core.model_schemas import ProviderState
from sentinel.providers.provider_manager import ProviderManager


def test_provider_state_not_configured():
    pm = ProviderManager()
    state = pm.get_provider_state("nonexistent")
    assert state["state"] == ProviderState.NOT_INSTALLED
    assert state["configured"] is False


def test_provider_state_cloud_ready_with_key():
    pm = ProviderManager()
    pm.set_api_key("openai", "sk-test")
    state = pm.get_provider_state("openai")
    assert state["state"] == ProviderState.READY
    assert state["configured"] is True
    assert state["authenticated"] is True


def test_provider_state_cloud_missing_key():
    pm = ProviderManager()
    state = pm.get_provider_state("openai")
    assert state["state"] == ProviderState.STOPPED
    assert state["configured"] is True
    assert state["authenticated"] is False


def test_model_state_follows_provider():
    pm = ProviderManager()
    state = pm.get_model_state("openai", "gpt-4o")
    assert state["configured"] is True
    assert state["authenticated"] is False
