import copy
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from conftest import admin_mode, confirm_mode
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


@pytest.mark.security
def test_permission_status_default():
    resp = client.post("/v1/execute", json={"tool_id": "permissions.status", "params": {}})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "level" in data
    assert "emergency_stop" in data
    assert data["emergency_stop"] == False
    assert data["level"] == "confirm"


@pytest.mark.security
def test_set_permission_level():
    admin_mode()
    for level in ["view", "confirm", "auto", "admin"]:
        admin_mode()
        resp = client.post("/v1/execute", json={"tool_id": "permissions.set_level", "params": {"level": level}})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "ok"


@pytest.mark.security
def test_set_invalid_level():
    admin_mode()
    resp = client.post("/v1/execute", json={"tool_id": "permissions.set_level", "params": {"level": "invalid"}})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "ok"


@pytest.mark.security
def test_emergency_stop():
    admin_mode()
    resp = client.post("/v1/execute", json={"tool_id": "permissions.emergency", "params": {"action": "stop"}})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "emergency_stop_activated"


@pytest.mark.security
def test_emergency_resume():
    admin_mode()
    client.post("/v1/execute", json={"tool_id": "permissions.emergency", "params": {"action": "stop"}})
    resp = client.post("/v1/execute", json={"tool_id": "permissions.emergency", "params": {"action": "resume"}})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "emergency_stop_deactivated"


@pytest.mark.security
def test_emergency_stop_remains_observable_and_recoverable():
    admin_mode()
    try:
        client.post(
            "/v1/execute",
            json={"tool_id": "permissions.emergency", "params": {"action": "stop"}},
        )
        status = client.post(
            "/v1/execute",
            json={"tool_id": "permissions.status", "params": {}},
        )
        assert status.status_code == 200
        assert status.json()["success"] is True
        assert status.json()["data"]["emergency_stop"] is True

        resumed = client.post(
            "/v1/execute",
            json={"tool_id": "permissions.emergency", "params": {"action": "resume"}},
        )
        assert resumed.json()["data"]["status"] == "emergency_stop_deactivated"
    finally:
        from modules.permissions import _svc as permission_service

        permission_service.emergency("resume")


@pytest.mark.security
def test_audit_log_default():
    resp = client.get("/v1/audit")
    assert resp.status_code == 200
    data = resp.json()
    assert "entries" in data
    assert "total" in data


@pytest.mark.security
def test_audit_log_after_command():
    admin_mode()
    client.post(
        "/v1/execute", json={"tool_id": "executor.command", "params": {"command": "echo audit_test", "timeout": 5}}
    )
    resp = client.get("/v1/audit")
    data = resp.json()
    entries = data["entries"]
    assert len(entries) >= 1
    assert any("audit_test" in str(e.get("details", "")) for e in entries)


@pytest.mark.security
def test_audit_log_limit():
    resp = client.get("/v1/audit?limit=5")
    data = resp.json()
    assert len(data["entries"]) <= 5


@pytest.mark.security
def test_audit_is_append_only():
    resp = client.delete("/v1/audit")
    assert resp.status_code == 405


@pytest.mark.security
def test_pending_action_flow():
    confirm_mode()
    resp = client.post(
        "/v1/execute", json={"tool_id": "executor.command", "params": {"command": "rm test_file", "timeout": 10}}
    )
    assert resp.status_code == 200
    assert resp.json()["requires_confirmation"] == True


@pytest.mark.security
def test_command_blocked_at_view_level():
    from modules.permissions import _svc as perm_svc

    perm_svc.set_level("view")
    resp = client.post(
        "/v1/execute", json={"tool_id": "executor.command", "params": {"command": "echo blocked_test", "timeout": 5}}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False or (body["requires_confirmation"] and body["data"].get("blocked"))


class _ConcurrentPermissionsRepository:
    def __init__(self):
        self.data = {"level": "confirm", "blocklist": [], "granular_rules": []}

    def load(self):
        time.sleep(0.001)
        return copy.deepcopy(self.data)

    def save(self, data):
        time.sleep(0.001)
        self.data = copy.deepcopy(data)


@pytest.mark.unit
def test_concurrent_permission_updates_do_not_overwrite_each_other():
    from services.permissions_service import PermissionsService

    repository = _ConcurrentPermissionsRepository()
    service = PermissionsService(repo=repository, state_lock=threading.RLock())

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(
            pool.map(
                lambda index: service.add_rule({"tool": f"tool-{index}", "effect": "allow"}),
                range(24),
            )
        )

    assert len(service.list_rules()) == 24
