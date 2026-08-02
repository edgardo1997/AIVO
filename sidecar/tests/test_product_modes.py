"""Unit tests for the unified product ModesService (FASE 8)."""

import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from sentinel.product.modes import ModesService, build_mode_catalog


class FakeStorage:
    def __init__(self):
        self.data = {}

    def config_get_json(self, key, default=None):
        return self.data.get(key, default)

    def config_set_json(self, key, value):
        self.data[key] = value


def fake_applier(mode_id):
    return [f"apply:{mode_id}"]


@pytest.fixture
def storage():
    return FakeStorage()


@pytest.fixture
def service(storage):
    return ModesService(storage=storage, applier=fake_applier)


def test_catalog_has_all_product_modes():
    catalog = build_mode_catalog()
    ids = {m["id"] for m in catalog}
    assert ids == {"developer", "gaming", "work", "privacy", "performance"}


def test_list_modes_returns_cards(service):
    modes = service.list_modes()
    assert len(modes) == 5
    for mode in modes:
        assert mode["name"]
        assert mode["description"]
        assert mode["capabilities"]
        assert mode["active"] is False


def test_activate_developer(service):
    result = service.activate("developer", _platform_apply=True)
    assert result["success"] is True
    assert result["mode_id"] == "developer"
    assert "apply:developer" in result["actions"]
    assert service.status()["active_mode"] == "developer"
    assert service.model_priority() == "coding"


def test_activate_snapshots_previous(service):
    service.activate("developer")
    result = service.activate("gaming")
    assert result["previous"] == "developer"
    assert service.status()["rollback_available"] is True
    history = service.status()["history"]
    assert history[-1]["mode_id"] == "developer"


def test_rollback_restores_previous(service):
    service.activate("developer")
    service.activate("gaming")
    result = service.rollback()
    assert result["success"] is True
    assert result["mode_id"] == "developer"


def test_deactivate_clears_active(service):
    service.activate("work")
    result = service.deactivate()
    assert result["mode_id"] is None
    assert service.status()["active_mode"] is None


def test_unknown_mode_fails(service):
    result = service.activate("unknown-mode")
    assert result["success"] is False
    assert "error" in result


def test_state_persists_across_instances(storage):
    first = ModesService(storage=storage, applier=fake_applier)
    first.activate("privacy")
    second = ModesService(storage=storage, applier=fake_applier)
    assert second.status()["active_mode"] == "privacy"
    assert second.model_priority() == "local"


def test_rollback_requires_history(service):
    result = service.rollback()
    assert result["success"] is False
    assert result["rollback_available"] is False


def test_activate_same_mode_is_idempotent(service):
    service.activate("performance")
    result = service.activate("performance")
    assert result.get("already_active") is True
    assert result["success"] is True


def test_recommended_mode_is_safe(service):
    recommended = service.recommended_mode()
    if recommended is not None:
        assert recommended in {"developer", "gaming", "work", "privacy", "performance"}
