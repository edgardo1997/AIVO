from conftest import admin_mode, confirm_mode
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_permission_status_default():
    resp = client.post("/v1/execute", json={"tool_id": "permissions.status", "params": {}})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "level" in data
    assert "emergency_stop" in data
    assert data["emergency_stop"] == False
    assert data["level"] == "confirm"

def test_set_permission_level():
    admin_mode()
    for level in ["view", "confirm", "auto", "admin"]:
        resp = client.post("/v1/execute", json={"tool_id": "permissions.set_level", "params": {"level": level}})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "ok"

def test_set_invalid_level():
    admin_mode()
    resp = client.post("/v1/execute", json={"tool_id": "permissions.set_level", "params": {"level": "invalid"}})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "ok"

def test_emergency_stop():
    resp = client.post("/v1/execute", json={"tool_id": "permissions.emergency", "params": {"action": "stop"}})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "emergency_stop_activated"

def test_emergency_resume():
    client.post("/v1/execute", json={"tool_id": "permissions.emergency", "params": {"action": "stop"}})
    resp = client.post("/v1/execute", json={"tool_id": "permissions.emergency", "params": {"action": "resume"}})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "emergency_stop_deactivated"

def test_audit_log_default():
    resp = client.get("/v1/audit")
    assert resp.status_code == 200
    data = resp.json()
    assert "entries" in data
    assert "total" in data

def test_audit_log_after_command():
    admin_mode()
    client.post("/v1/execute", json={"tool_id": "executor.command", "params": {"command": "echo audit_test", "timeout": 5}})
    resp = client.get("/v1/audit")
    data = resp.json()
    entries = data["entries"]
    assert len(entries) >= 1
    assert any("audit_test" in str(e.get("details", "")) for e in entries)

def test_audit_log_limit():
    resp = client.get("/v1/audit?limit=5")
    data = resp.json()
    assert len(data["entries"]) <= 5

def test_audit_is_append_only():
    resp = client.delete("/v1/audit")
    assert resp.status_code == 405

def test_pending_action_flow():
    confirm_mode()
    resp = client.post("/v1/execute", json={"tool_id": "executor.command", "params": {"command": "rm test_file", "timeout": 10}})
    assert resp.status_code == 200
    assert resp.json()["requires_confirmation"] == True

def test_command_blocked_at_view_level():
    from modules.permissions import _svc as perm_svc
    perm_svc.set_level("view")
    resp = client.post("/v1/execute", json={"tool_id": "executor.command", "params": {"command": "echo blocked_test", "timeout": 5}})
    assert resp.status_code == 200
    assert resp.json()["success"] == False
    assert "deny" in resp.json()["error"].lower()
