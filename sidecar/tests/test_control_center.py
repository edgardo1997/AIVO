"""Unit tests for the System Control Center service (FASE 8)."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from sentinel.product.control_center import ControlCenterService


class _FakeOptimizer:
    class _Result:
        success = True
        mode = "balanced"
        actions = ["power_plan=balanced"]
        errors = []
        context = {"cpu_usage": 12.0, "memory_usage": 40.0, "games": [], "ides": []}
        snapshot_id = "snap-1"

    def optimize_dry_run(self):
        return self._Result()

    def optimize(self):
        return self._Result()


@pytest.fixture
def service():
    return ControlCenterService(storage=None, optimizer=_FakeOptimizer())


def test_overview_structure(service):
    overview = service.overview()
    assert "resources" in overview
    assert "processes" in overview
    assert "applications" in overview
    assert "network" in overview
    assert isinstance(overview["recommendations"], list)


def test_optimize_dry_run(service):
    result = service.optimize(dry_run=True)
    assert result["success"] is True
    assert result["dry_run"] is True
    assert result["mode"] == "balanced"


def test_free_resources_is_preview_by_default(service):
    result = service.free_resources(commit=False)
    assert result["preview"] is True
    assert result["terminated"] == []


def test_create_profile(service):
    result = service.create_profile(name="test-profile")
    assert result["success"] is True
    assert result["name"] == "test-profile"


def test_create_profile_reports_snapshot_failure(service, monkeypatch):
    from sentinel.core import environment_snapshot

    def fail_snapshot(_name):
        raise OSError("snapshot storage unavailable")

    monkeypatch.setattr(environment_snapshot, "create_snapshot", fail_snapshot)
    result = service.create_profile(name="test-profile")
    assert result == {
        "success": False,
        "name": "test-profile",
        "error": "No se pudo crear el perfil de estado.",
    }
