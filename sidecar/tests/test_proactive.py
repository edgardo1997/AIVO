from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_suggestions_endpoint():
    resp = client.get("/api/proactive/suggestions")
    assert resp.status_code == 200
    data = resp.json()
    assert "suggestions" in data
    assert "trends" in data
    assert "engine_active" in data
    assert isinstance(data["suggestions"], list)
    assert isinstance(data["engine_active"], bool)

def test_metrics_history_endpoint():
    resp = client.get("/api/proactive/metrics-history")
    assert resp.status_code == 200
    data = resp.json()
    assert "history" in data
    assert isinstance(data["history"], list)

def test_engine_restart():
    resp = client.post("/api/proactive/engine/restart")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "restarted"

def test_dismiss_suggestion():
    # Get current suggestions (if any)
    resp = client.get("/api/proactive/suggestions")
    suggestions = resp.json()["suggestions"]
    if suggestions:
        sid = suggestions[0]["id"]
        resp = client.post(f"/api/proactive/suggestions/{sid}/dismiss")
        assert resp.status_code == 200
        assert resp.json()["status"] == "dismissed"

def test_dismiss_nonexistent():
    resp = client.post("/api/proactive/suggestions/nonexistent_id/dismiss")
    assert resp.status_code == 200
    assert resp.json()["status"] == "not_found"

def test_api_info():
    resp = client.get("/api/info")
    assert resp.status_code == 200
    data = resp.json()
    assert "name" in data
    assert "version" in data
    assert "modules" in data
    assert len(data["modules"]) >= 9  # monitor, executor, ai, filesystem, permissions, audit, proactive, plugins, voice, fleet
