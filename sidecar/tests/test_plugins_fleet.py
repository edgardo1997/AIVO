import os
import pytest
import json
import tempfile
from fastapi.testclient import TestClient
from main import app
from modules.permissions import _svc as perm_svc

client = TestClient(app)


def admin_mode():
    perm_svc.set_level("admin")


@pytest.fixture(autouse=True)
def clean_plugin_state():
    from modules.plugins import ACTIVE_PLUGINS, PLUGIN_STATES, PLUGIN_METADATA, PLUGIN_DIR
    import shutil

    ACTIVE_PLUGINS.clear()
    PLUGIN_STATES.clear()
    PLUGIN_METADATA.clear()
    test_plugins = ["test_plugin", "dup_plugin"]
    for p in test_plugins:
        path = os.path.join(PLUGIN_DIR, p)
        if os.path.exists(path):
            shutil.rmtree(path, ignore_errors=True)
    yield


def test_list_plugins():
    admin_mode()
    resp = client.post("/v1/execute", json={"tool_id": "plugins.list", "params": {}})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "plugins" in data
    assert isinstance(data["plugins"], list)


def test_list_templates():
    admin_mode()
    resp = client.post("/v1/execute", json={"tool_id": "plugins.templates", "params": {}})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "templates" in data
    assert "minimal" in data["templates"]
    assert "system_health" in data["templates"]
    assert "media_control" in data["templates"]


def test_create_and_load_plugin():
    admin_mode()
    resp = client.post(
        "/v1/execute", json={"tool_id": "plugins.create", "params": {"name": "test_plugin", "template": "minimal"}}
    )
    assert resp.status_code == 200
    assert resp.json()["success"] == True
    data = resp.json()["data"]
    assert data["status"] == "created"

    resp = client.post("/v1/execute", json={"tool_id": "plugins.load", "params": {"plugin_id": "test_plugin"}})
    assert resp.status_code == 200
    assert resp.json()["success"] == True

    resp = client.post("/v1/execute", json={"tool_id": "plugins.unload", "params": {"plugin_id": "test_plugin"}})
    assert resp.status_code == 200

    resp = client.post("/v1/execute", json={"tool_id": "plugins.toggle", "params": {"plugin_id": "test_plugin"}})
    assert resp.status_code == 200


def test_create_duplicate_plugin():
    admin_mode()
    resp = client.post(
        "/v1/execute", json={"tool_id": "plugins.create", "params": {"name": "dup_plugin", "template": "minimal"}}
    )
    assert resp.json()["success"] == True
    resp = client.post(
        "/v1/execute", json={"tool_id": "plugins.create", "params": {"name": "dup_plugin", "template": "minimal"}}
    )
    assert resp.status_code == 200
    assert resp.json()["success"] == False


def test_load_nonexistent_plugin():
    admin_mode()
    resp = client.post("/v1/execute", json={"tool_id": "plugins.load", "params": {"plugin_id": "nonexistent"}})
    assert resp.status_code == 200
    assert resp.json()["success"] == False


def test_unload_nonexistent_plugin():
    admin_mode()
    resp = client.post("/v1/execute", json={"tool_id": "plugins.unload", "params": {"plugin_id": "nonexistent"}})
    assert resp.status_code == 200
    assert resp.json()["success"] == True


def test_fleet_status():
    admin_mode()
    resp = client.post("/v1/execute", json={"tool_id": "fleet.status", "params": {}})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "remote_enabled" in data
    assert "local_ip" in data
    assert "api_port" in data


def test_fleet_generate_and_revoke():
    admin_mode()
    resp = client.post("/v1/execute", json={"tool_id": "fleet.generate_pairing", "params": {}})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "token" in data
    token = data["token"]
    assert len(token) == 64
    from modules.fleet import _svc as fleet_service

    stored = fleet_service.repo.load()
    assert stored["pairing_token"] == ""
    assert len(stored["pairing_token_hash"]) == 64

    resp = client.post("/v1/execute", json={"tool_id": "fleet.revoke_pairing", "params": {}})
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "revoked"


def test_fleet_toggle_remote():
    admin_mode()
    resp = client.post("/v1/execute", json={"tool_id": "fleet.toggle_remote", "params": {}})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "enabled" in data


def test_fleet_qr():
    admin_mode()
    client.post("/v1/execute", json={"tool_id": "fleet.generate_pairing", "params": {}})
    resp = client.post("/v1/execute", json={"tool_id": "fleet.qr", "params": {}})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "qr_data" in data
    assert "sentinel://" in data["qr_data"]
