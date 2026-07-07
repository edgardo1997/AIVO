from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_permission_status_default():
    resp = client.get("/api/permissions/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "level" in data
    assert "emergency_stop" in data
    assert data["emergency_stop"] == False
    assert data["level"] == "confirm"

def test_set_permission_level():
    for level in ["view", "confirm", "auto", "admin"]:
        resp = client.post("/api/permissions/level", json={"level": level})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "saved"

def test_set_invalid_level():
    resp = client.post("/api/permissions/level", json={"level": "invalid"})
    assert resp.status_code == 422

def test_emergency_stop():
    resp = client.post("/api/permissions/emergency/stop")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "emergency_stop"

def test_emergency_resume():
    resp = client.post("/api/permissions/emergency/stop")
    resp = client.post("/api/permissions/emergency/resume")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "resumed"

def test_audit_log_default():
    resp = client.get("/api/audit/log")
    assert resp.status_code == 200
    data = resp.json()
    assert "entries" in data
    assert "total" in data

def test_audit_log_after_command():
    client.post("/api/executor/command", json={"command": "echo audit_test", "timeout": 5})
    resp = client.get("/api/audit/log")
    data = resp.json()
    entries = data["entries"]
    assert len(entries) >= 1
    assert any("audit_test" in e.get("detail", "") for e in entries)

def test_audit_log_limit():
    resp = client.get("/api/audit/log?limit=5")
    data = resp.json()
    assert len(data["entries"]) <= 5

def test_audit_clear():
    resp = client.delete("/api/audit/log")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "cleared"

def test_pending_action_flow():
    resp = client.post("/api/executor/command", json={
        "command": "rm test_file",
        "timeout": 10,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("needs_confirm", False)
    action_id = data.get("action_id", "")
    assert action_id != ""

def test_command_blocked_at_view_level():
    client.post("/api/permissions/level", json={"level": "view"})
    resp = client.post("/api/executor/command", json={
        "command": "echo blocked_test",
        "timeout": 5,
    })
    data = resp.json()
    assert data["returncode"] == -1
    assert "denied" in data["stderr"].lower() or "view" in data["stderr"].lower()
