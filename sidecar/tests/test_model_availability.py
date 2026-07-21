from types import SimpleNamespace

import pytest

from sentinel.core.model_router import (
    BUILTIN_PROVIDERS,
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


def test_nvidia_nemotron_is_registered_but_requires_a_key():
    nvidia = next(provider for provider in BUILTIN_PROVIDERS if provider.id == "nvidia")

    assert nvidia.default_model == "nvidia/nemotron-3-super-120b-a12b"
    assert nvidia.requires_key is True
    assert TaskType.REASONING in nvidia.task_types


def test_provider_key_is_kept_out_of_plaintext_configuration(tmp_path):
    from repositories.ai_repository import AIRepository
    from services.ai_service import AIService

    class FakeVault:
        def __init__(self):
            self.values = {}

        def get_entry(self, vault_id):
            return SimpleNamespace(id=vault_id) if vault_id in self.values else None

        def create_entry(self, entry):
            self.values[entry.id] = entry.value
            return entry.id

        def update_entry(self, vault_id, **updates):
            self.values[vault_id] = updates["value"]
            return True

        def list_entries(self, category=""):
            return [SimpleNamespace(id=key) for key in self.values]

        def reveal_value(self, vault_id):
            return self.values.get(vault_id)

    config_path = tmp_path / "ai-config.json"
    service = AIService(repo=AIRepository(filepath=str(config_path)))
    service.set_router(ModelRouter())
    vault = FakeVault()
    service.set_vault(vault)

    service.set_config({
        "provider": "nvidia",
        "api_key": "nvapi-test-secret",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "model": "nvidia/nemotron-3-super-120b-a12b",
        "strategy": "manual",
    })

    assert "nvapi-test-secret" not in config_path.read_text()
    assert vault.values["ai-provider-nvidia"] == "nvapi-test-secret"
    assert service.get_config()["api_key"] == ""
    assert service.get_config()["api_key_configured"] is True

    service.set_config({
        "provider": "nvidia",
        "api_key": "set",
        "model": "nvidia/nemotron-3-super-120b-a12b",
    })
    assert vault.values["ai-provider-nvidia"] == "nvapi-test-secret"

    restarted = AIService(repo=AIRepository(filepath=str(config_path)), router=ModelRouter())
    restarted.set_vault(vault)
    restarted.load_provider_keys()
    assert restarted.get_config()["provider"] == "nvidia"
    assert restarted.get_config()["api_key_configured"] is True
    assert restarted._router.has_api_key("nvidia") is True


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


def test_user_preferred_provider_wins_when_it_is_available():
    fast = ProviderSpec(
        id="fast",
        name="Fast",
        task_types=[TaskType.QUICK],
        requires_key=False,
        priority=100,
    )
    private = ProviderSpec(
        id="private",
        name="Private",
        task_types=[TaskType.QUICK],
        requires_key=False,
        priority=10,
    )
    router = ModelRouter(providers=[fast, private])
    router.set_preferred_provider("private")

    assert router.select(TaskType.QUICK).provider_id == "private"


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
    assert "hardware" in payload
    assert "gpus" not in payload["hardware"]
    assert "ram_total_gb" in payload["hardware"]
