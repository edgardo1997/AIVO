import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from main import app
from modules import get_sentinel_goal_registry, proactive as proactive_mod
from repositories import async_engine

client = TestClient(app)


def test_api_info():
    resp = client.get("/api/info")
    assert resp.status_code == 200
    data = resp.json()
    assert "name" in data
    assert "version" in data
    assert "modules" in data
    assert len(data["modules"]) >= 9


@pytest.mark.skip(reason="No V1 endpoint for proactive suggestions")
def test_proactive_suggestions():
    resp = client.get("/api/proactive/suggestions")
    assert resp.status_code == 200
    data = resp.json()
    assert "suggestions" in data
    assert "trends" in data


def test_health():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.integration
def test_runtime_services_follow_application_lifespan():
    proactive_mod._svc.stop()

    with TestClient(app) as runtime_client:
        assert runtime_client.get("/api/health").status_code == 200
        assert runtime_client.get("/api/sentinel/goals").status_code == 200
        assert proactive_mod._svc._engine_thread is not None
        assert proactive_mod._svc._engine_thread.is_alive()
        assert async_engine._async_engine_instance is not None
        assert get_sentinel_goal_registry() is not None

    assert proactive_mod._svc._engine_thread is None
    assert proactive_mod._svc.engine_active is False
    assert async_engine._async_engine_instance is None
    assert get_sentinel_goal_registry() is None
