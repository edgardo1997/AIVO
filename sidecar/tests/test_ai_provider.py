import json
import os

import pytest

from modules import ai_provider
from modules.ai_provider import (
    ConfigModel,
    FREE_PROVIDERS,
    load_config,
    save_config,
    get_client,
)


@pytest.fixture
def config_path(tmp_path, monkeypatch):
    path = str(tmp_path / "config.json")
    monkeypatch.setattr(ai_provider, "CONFIG_FILE", path)
    return path


class FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeChoice:
    def __init__(self, content):
        self.message = FakeMessage(content)


class FakeResponse:
    def __init__(self, content):
        self.choices = [FakeChoice(content)]


class FakeCompletions:
    def __init__(self, content=None, error=None):
        self._content = content
        self._error = error
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return FakeResponse(self._content)


class FakeClient:
    def __init__(self, content=None, error=None):
        self.chat = type("Chat", (), {})()
        self.chat.completions = FakeCompletions(content=content, error=error)


def install_fake_client(monkeypatch, content=None, error=None):
    fake = FakeClient(content=content, error=error)
    monkeypatch.setattr(ai_provider, "get_client", lambda cfg: fake)
    return fake


# --- FREE_PROVIDERS ---

def test_free_providers_have_required_fields():
    for name, info in FREE_PROVIDERS.items():
        assert "label" in info
        assert "default_model" in info
        assert "description" in info
        assert "signup_url" in info
        assert "base_url" in info


# --- load_config ---

def test_load_config_defaults_when_no_file(config_path):
    cfg = load_config()
    assert cfg.provider == "openrouter"
    assert cfg.model == FREE_PROVIDERS["openrouter"]["default_model"]
    assert cfg.base_url == FREE_PROVIDERS["openrouter"]["base_url"]


def test_load_config_fills_missing_model_and_base_url(config_path):
    with open(config_path, "w") as f:
        json.dump({"provider": "groq", "api_key": "k"}, f)
    cfg = load_config()
    assert cfg.provider == "groq"
    assert cfg.api_key == "k"
    assert cfg.model == FREE_PROVIDERS["groq"]["default_model"]
    assert cfg.base_url == FREE_PROVIDERS["groq"]["base_url"]


def test_load_config_keeps_explicit_values(config_path):
    with open(config_path, "w") as f:
        json.dump(
            {
                "provider": "openai",
                "api_key": "k",
                "model": "custom-model",
                "base_url": "http://custom",
            },
            f,
        )
    cfg = load_config()
    assert cfg.model == "custom-model"
    assert cfg.base_url == "http://custom"


# --- save_config ---

def test_save_config_round_trip(config_path):
    cfg = ConfigModel(provider="mistral", api_key="secret", model="m", base_url="http://b")
    save_config(cfg)
    assert os.path.exists(config_path)
    loaded = load_config()
    assert loaded.provider == "mistral"
    assert loaded.api_key == "secret"
    assert loaded.model == "m"


# --- get_client ---

def test_get_client_openrouter_sets_referer_headers():
    cfg = ConfigModel(provider="openrouter", api_key="k", base_url="http://x")
    client = get_client(cfg)
    assert client.base_url is not None


def test_get_client_uses_default_base_url_when_missing():
    cfg = ConfigModel(provider="openai", api_key="k", base_url=None)
    client = get_client(cfg)
    assert client is not None


# --- /chat endpoint ---

def test_chat_success(client, config_path, monkeypatch):
    fake = install_fake_client(monkeypatch, content="hello there")
    resp = client.post("/api/ai/chat", json={"message": "hi"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["response"] == "hello there"
    assert data["provider"] == "openrouter"
    # system prompt + user message
    sent = fake.chat.completions.calls[0]["messages"]
    assert sent[0]["role"] == "system"
    assert sent[-1] == {"role": "user", "content": "hi"}


def test_chat_includes_context(client, config_path, monkeypatch):
    fake = install_fake_client(monkeypatch, content="ok")
    context = [{"role": "user", "content": "prev"}, {"role": "assistant", "content": "reply"}]
    resp = client.post("/api/ai/chat", json={"message": "next", "context": context})
    assert resp.status_code == 200
    sent = fake.chat.completions.calls[0]["messages"]
    assert {"role": "user", "content": "prev"} in sent
    assert sent[-1]["content"] == "next"


def test_chat_provider_override(client, config_path, monkeypatch):
    fake = install_fake_client(monkeypatch, content="ok")
    resp = client.post("/api/ai/chat", json={"message": "hi", "provider": "groq"})
    assert resp.status_code == 200
    assert resp.json()["provider"] == "groq"
    assert fake.chat.completions.calls[0]["model"] == FREE_PROVIDERS["groq"]["default_model"]


def test_chat_invalid_api_key_returns_401(client, config_path, monkeypatch):
    install_fake_client(monkeypatch, error=Exception("401 unauthorized"))
    resp = client.post("/api/ai/chat", json={"message": "hi"})
    assert resp.status_code == 401
    assert "Invalid API key" in resp.json()["detail"]


def test_chat_model_not_available_returns_400(client, config_path, monkeypatch):
    install_fake_client(monkeypatch, error=Exception("model does not exist / not found"))
    resp = client.post("/api/ai/chat", json={"message": "hi"})
    assert resp.status_code == 400
    assert "not available" in resp.json()["detail"]


def test_chat_generic_error_returns_500(client, config_path, monkeypatch):
    install_fake_client(monkeypatch, error=Exception("boom network failure"))
    resp = client.post("/api/ai/chat", json={"message": "hi"})
    assert resp.status_code == 500
    assert "boom" in resp.json()["detail"]


# --- /analyze endpoint ---

def test_analyze_success(client, config_path, monkeypatch):
    install_fake_client(monkeypatch, content="all good")
    resp = client.post("/api/ai/analyze", json={"metrics": {"cpu": 10}})
    assert resp.status_code == 200
    assert resp.json()["analysis"] == "all good"


def test_analyze_failure_returns_graceful_message(client, config_path, monkeypatch):
    install_fake_client(monkeypatch, error=Exception("down"))
    resp = client.post("/api/ai/analyze", json={"metrics": {"cpu": 10}})
    assert resp.status_code == 200
    data = resp.json()
    assert data["model"] == "none"
    assert "unavailable" in data["analysis"].lower()


# --- /config endpoints ---

def test_get_config_endpoint(client, config_path):
    resp = client.get("/api/ai/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "provider" in data
    assert "free_providers" in data
    assert "openrouter" in data["free_providers"]


def test_set_config_fills_defaults(client, config_path):
    resp = client.post("/api/ai/config", json={"provider": "cerebras", "api_key": "k"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "saved"
    saved = load_config()
    assert saved.model == FREE_PROVIDERS["cerebras"]["default_model"]
    assert saved.base_url == FREE_PROVIDERS["cerebras"]["base_url"]
