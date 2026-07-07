import pytest
import os
import json
import tempfile
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

# Fixture to clean plugin state
@pytest.fixture(autouse=True)
def clean_plugin_state():
    from modules.plugins import ACTIVE_PLUGINS, PLUGIN_STATES, PLUGIN_METADATA
    ACTIVE_PLUGINS.clear()
    PLUGIN_STATES.clear()
    PLUGIN_METADATA.clear()
    yield

def test_list_plugins():
    resp = client.get("/api/plugins/list")
    assert resp.status_code == 200
    data = resp.json()
    assert "plugins" in data
    assert isinstance(data["plugins"], list)

def test_list_templates():
    resp = client.get("/api/plugins/templates")
    assert resp.status_code == 200
    data = resp.json()
    assert "templates" in data
    assert "minimal" in data["templates"]
    assert "system_health" in data["templates"]
    assert "media_control" in data["templates"]

def test_create_and_load_plugin():
    resp = client.post("/api/plugins/create", json={
        "name": "test_plugin",
        "template": "minimal",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "created"

    resp = client.post("/api/plugins/test_plugin/load")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "loaded" or data["status"] == "error"

    resp = client.post("/api/plugins/test_plugin/unload")
    assert resp.status_code == 200

    resp = client.post("/api/plugins/test_plugin/toggle")
    assert resp.status_code == 200

def test_create_duplicate_plugin():
    client.post("/api/plugins/create", json={"name": "dup_plugin", "template": "minimal"})
    resp = client.post("/api/plugins/create", json={"name": "dup_plugin", "template": "minimal"})
    assert resp.status_code == 400

def test_load_nonexistent_plugin():
    resp = client.post("/api/plugins/nonexistent/load")
    assert resp.status_code == 404

def test_unload_nonexistent_plugin():
    resp = client.post("/api/plugins/nonexistent/unload")
    assert resp.status_code == 200  # unload is idempotent

def test_voice_voices():
    resp = client.get("/api/voice/voices")
    assert resp.status_code == 200
    data = resp.json()
    assert "voices" in data
    assert len(data["voices"]) > 0
    assert data["voices"][0]["id"] == "en-US-JennyNeural"

def test_stt():
    resp = client.post("/api/voice/stt")
    assert resp.status_code == 501  # browser-only feature

def test_fleet_status():
    resp = client.get("/api/fleet/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "remote_enabled" in data
    assert "local_ip" in data
    assert "api_port" in data

def test_fleet_generate_and_revoke():
    resp = client.post("/api/fleet/pairing/generate")
    assert resp.status_code == 200
    data = resp.json()
    assert "token" in data
    token = data["token"]
    assert len(token) == 8

    resp = client.post("/api/fleet/pairing/revoke")
    assert resp.status_code == 200
    assert resp.json()["status"] == "revoked"

def test_fleet_toggle_remote():
    resp = client.post("/api/fleet/remote/toggle")
    assert resp.status_code == 200
    data = resp.json()
    assert "enabled" in data

def test_fleet_qr():
    client.post("/api/fleet/pairing/generate")
    resp = client.get("/api/fleet/pairing/qr")
    assert resp.status_code == 200
    data = resp.json()
    assert "qr_data" in data
    assert "aivo://" in data["qr_data"]
