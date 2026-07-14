import pytest

from sentinel.core.model_router import (
    ModelRouter,
    ProviderAvailability,
    ProviderSpec,
    TaskType,
)


def status(provider_id: str, available: bool, reason: str):
    return ProviderAvailability(provider_id, available, reason, 1.0)


def test_remote_provider_without_key_is_never_selected():
    remote = ProviderSpec(
        id="openrouter",
        name="OpenRouter",
        task_types=[TaskType.QUICK],
        requires_key=True,
        priority=100,
    )
    local = ProviderSpec(
        id="ollama",
        name="Ollama",
        task_types=[TaskType.QUICK],
        requires_key=False,
        is_local=True,
        priority=10,
    )
    router = ModelRouter(
        providers=[remote, local],
        availability_checker=lambda provider: status(provider.id, True, "reachable"),
    )

    decision = router.select(TaskType.QUICK)

    assert decision.provider_id == "ollama"
    assert decision.selection_trace["excluded"]["openrouter"] == "missing_api_key"


def test_ollama_must_be_reachable_before_selection():
    local = ProviderSpec(
        id="ollama",
        name="Ollama",
        task_types=[TaskType.QUICK],
        requires_key=False,
        is_local=True,
    )
    router = ModelRouter(
        providers=[local],
        availability_checker=lambda provider: status(provider.id, False, "connection_refused"),
    )

    with pytest.raises(RuntimeError, match="No available provider"):
        router.select(TaskType.QUICK)


def test_configured_remote_is_explicit_fallback_when_local_is_down():
    local = ProviderSpec(
        id="ollama",
        name="Ollama",
        task_types=[TaskType.QUICK],
        requires_key=False,
        is_local=True,
        priority=100,
    )
    remote = ProviderSpec(
        id="openrouter",
        name="OpenRouter",
        task_types=[TaskType.QUICK],
        requires_key=True,
        priority=10,
    )
    router = ModelRouter(
        providers=[local, remote],
        availability_checker=lambda provider: status(provider.id, False, "local_offline"),
    )
    router.set_api_key("openrouter", "test-key")

    decision = router.select(TaskType.QUICK)

    assert decision.provider_id == "openrouter"
    assert decision.selection_trace["excluded"]["ollama"] == "local_offline"


def test_decision_reason_and_history_are_auditable():
    remote = ProviderSpec(
        id="openrouter",
        name="OpenRouter",
        task_types=[TaskType.REASONING],
        requires_key=True,
        default_model="model-a",
    )
    router = ModelRouter(providers=[remote])
    router.set_api_key("openrouter", "test-key")

    decision = router.select(TaskType.REASONING)
    history = router.routing_history()

    assert "availability=verified" in decision.reason
    assert history[-1]["provider_id"] == "openrouter"
    assert history[-1]["selection_trace"]["eligible"] == ["openrouter"]


def test_manual_ollama_call_refuses_unreachable_service():
    local = ProviderSpec(
        id="ollama",
        name="Ollama",
        task_types=[TaskType.QUICK],
        requires_key=False,
        is_local=True,
    )
    router = ModelRouter(
        providers=[local],
        availability_checker=lambda provider: status(provider.id, False, "not_running"),
    )

    with pytest.raises(RuntimeError, match="not_running"):
        router.chat_with_provider([{"role": "user", "content": "hello"}], "ollama", "llama3")


def test_router_status_endpoint_never_exposes_keys():
    from fastapi.testclient import TestClient
    from main import app

    response = TestClient(app).get("/api/sentinel/model-router/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["enabled"] is True
    assert "providers" in payload
    assert "recent_decisions" in payload
    assert all("api_key" not in provider for provider in payload["providers"])
