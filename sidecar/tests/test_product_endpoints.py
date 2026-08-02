"""API tests for the Product Experience endpoints (FASE 8)."""

import os
import sys
import tempfile

_temp_product_dir = tempfile.mkdtemp(prefix="sentinel-product-tests-")
os.environ["SENTINEL_PRODUCT_DIR"] = _temp_product_dir

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest


@pytest.fixture(autouse=True)
def clear_product_state():
    from modules.product_experience import _modes

    service = _modes()
    if service.status().get("active_mode"):
        service.deactivate()
    yield
    if service.status().get("active_mode"):
        service.deactivate()


def test_list_modes(client):
    response = client.get("/api/sentinel/product/modes")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 5
    ids = {item["id"] for item in payload}
    assert ids == {"developer", "gaming", "work", "privacy", "performance"}


def test_activate_deactivate_mode(client):
    response = client.post(
        "/api/sentinel/product/modes/developer/activate",
        json={"reason": "test", "platform_apply": False},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["mode_id"] == "developer"

    status = client.get("/api/sentinel/product/modes/status").json()
    assert status["active_mode"] == "developer"

    deactivate = client.post("/api/sentinel/product/modes/developer/deactivate", json={"reason": "test"}).json()
    assert deactivate["mode_id"] is None


def test_unknown_mode_activation(client):
    response = client.post("/api/sentinel/product/modes/unknown/activate", json={"platform_apply": False})
    assert response.status_code == 200
    assert response.json()["success"] is False


def test_mode_rollback(client):
    client.post("/api/sentinel/product/modes/developer/activate", json={"platform_apply": False})
    client.post("/api/sentinel/product/modes/gaming/activate", json={"platform_apply": False})
    response = client.post("/api/sentinel/product/modes/rollback").json()
    assert response["success"] is True
    assert response["mode_id"] == "developer"


def test_recommend_mode(client):
    response = client.post("/api/sentinel/product/modes/recommend")
    assert response.status_code == 200
    payload = response.json()
    assert "recommended" in payload
    assert "context" in payload


def test_model_center(client):
    response = client.get("/api/sentinel/product/model-center")
    assert response.status_code == 200
    payload = response.json()
    assert "models" in payload
    assert payload["count"] > 0


def test_model_favorite_and_priority(client):
    models = client.get("/api/sentinel/product/model-center").json()["models"]
    model_id = models[0]["id"]

    favorite = client.put("/api/sentinel/product/model-center/favorites", json={"model_id": model_id, "favorite": True})
    assert favorite.status_code == 200
    assert model_id in favorite.json()["favorites"]

    priority = client.put("/api/sentinel/product/model-center/priorities", json={"priority": "speed"})
    assert priority.status_code == 200
    assert priority.json()["priority"] == "speed"

    payload = client.get("/api/sentinel/product/model-center").json()
    assert payload["priority"] == "speed"
    assert model_id in payload["favorites"]


def test_model_unknown_favorite_404(client):
    response = client.put("/api/sentinel/product/model-center/favorites", json={"model_id": "no-such-model", "favorite": True})
    assert response.status_code == 404


def test_product_metrics_event_and_overview(client):
    event = client.post(
        "/api/sentinel/product/metrics/event",
        json={"event_type": "action_completed", "details": {"action": "test"}},
    )
    assert event.status_code == 200
    assert event.json()["success"] is True

    overview = client.get("/api/sentinel/product/metrics?days=14")
    assert overview.status_code == 200
    payload = overview.json()
    assert payload["actions_completed"] >= 1
    assert "retention" in payload
    assert "usage_by_mode" in payload


def test_control_center(client):
    response = client.get("/api/sentinel/product/control-center")
    assert response.status_code == 200
    payload = response.json()
    assert "resources" in payload
    assert isinstance(payload["recommendations"], list)


def test_control_optimize_dry_run(client):
    response = client.post("/api/sentinel/product/control-center/optimize", json={"dry_run": True})
    assert response.status_code == 200
    assert response.json()["dry_run"] is True


def test_control_free_resources_preview(client):
    response = client.post("/api/sentinel/product/control-center/free-resources", json={"commit": False})
    assert response.status_code == 200
    assert response.json()["preview"] is True


def test_control_create_profile(client):
    response = client.post("/api/sentinel/product/control-center/profile", json={"name": "beta-test"})
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_control_create_profile_failure_is_not_counted_as_completed(client, monkeypatch):
    from modules import get_gateway
    from modules import product_experience

    class FailedControl:
        def create_profile(self, name=""):
            return {"success": False, "name": name, "error": "snapshot unavailable"}

    class Metrics:
        def __init__(self):
            self.events = []

        def record(self, event_type, details):
            self.events.append((event_type, details))

    metrics = Metrics()
    monkeypatch.setattr(product_experience, "_metrics", lambda: metrics)
    monkeypatch.setattr(get_gateway()._tools["product.control.create_profile"], "_control", FailedControl())

    response = client.post("/api/sentinel/product/control-center/profile", json={"name": "beta-test"})
    assert response.status_code == 200
    assert response.json()["success"] is False
    assert metrics.events == []
