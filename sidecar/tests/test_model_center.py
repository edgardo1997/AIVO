"""Unit tests for the ModelCenterService (FASE 8)."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from sentinel.models import ModelMetadata, ModelStatus
from sentinel.core.model_registry import ModelRegistry
from sentinel.product.model_center import ModelCenterService


class FakeStorage:
    def __init__(self):
        self.data = {}

    def config_get_json(self, key, default=None):
        return self.data.get(key, default)

    def config_set_json(self, key, value):
        self.data[key] = value


@pytest.fixture
def storage():
    return FakeStorage()


@pytest.fixture
def registry():
    reg = ModelRegistry()
    reg.register_many(
        [
            ModelMetadata(
                id="qwen-local",
                provider="sentinel_local",
                context_window=4096,
                supports_coding=True,
                speed="slow",
                cost=0.0,
                local=True,
                status=ModelStatus.AVAILABLE,
                tags=["local"],
            ),
            ModelMetadata(
                id="gpt-fast",
                provider="openai",
                context_window=128000,
                supports_coding=True,
                supports_reasoning=True,
                speed="fast",
                cost=0.0,
                local=False,
                status=ModelStatus.AVAILABLE,
                tags=["fast", "coding"],
            ),
            ModelMetadata(
                id="vision-model",
                provider="gemini",
                context_window=1000000,
                supports_vision=True,
                speed="fast",
                cost=0.0,
                local=False,
                status=ModelStatus.AVAILABLE,
                tags=["vision"],
            ),
        ]
    )
    return reg


@pytest.fixture
def service(storage, registry):
    return ModelCenterService(storage=storage, registry=registry)


def test_list_models_returns_cards(service):
    payload = service.list_models()
    assert payload["count"] == 3
    assert payload["favorites"] == []
    assert payload["priority"] == "balanced"
    cards = {m["id"]: m for m in payload["models"]}
    qwen = cards["qwen-local"]
    assert qwen["kind"] == "local"
    assert qwen["speed_label"] in {"Muy alta", "Alta", "Media", "Lenta", "Desconocida"}
    assert "Código" in qwen["capability_labels"]


def test_set_favorite_persists(service):
    result = service.set_favorite("gpt-fast", True)
    assert result["success"] is True
    assert "gpt-fast" in result["favorites"]
    payload = service.list_models()
    assert payload["favorites"] == ["gpt-fast"]
    assert next(m for m in payload["models"] if m["id"] == "gpt-fast")["favorite"] is True


def test_unfavorite(service):
    service.set_favorite("gpt-fast", True)
    result = service.set_favorite("gpt-fast", False)
    assert result["favorites"] == []
    assert service.list_models()["favorites"] == []


def test_unknown_favorite_fails(service):
    result = service.set_favorite("nope", True)
    assert result["success"] is False


def test_set_priority(service):
    result = service.set_priority("speed")
    assert result["success"] is True
    assert service.list_models()["priority"] == "speed"


def test_invalid_priority_fails(service):
    result = service.set_priority("banana")
    assert result["success"] is False


def test_recommended_for_local(service):
    recommendation = service.recommended_for("local")
    assert recommendation is not None
    assert recommendation["local"] is True


def test_recommended_for_fast(service):
    recommendation = service.recommended_for("fast")
    assert recommendation is not None
    assert recommendation["speed"] in {"fast", "very_fast"}


def test_priority_persists_across_instances(storage, registry):
    first = ModelCenterService(storage=storage, registry=registry)
    first.set_priority("quality")
    second = ModelCenterService(storage=storage, registry=registry)
    assert second.list_models()["priority"] == "quality"
