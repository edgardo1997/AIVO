import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from main import app

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
