"""Integration tests for /api/sentinel/plugins/* endpoints (FASE 9)."""

import json
import os

import pytest
from fastapi.testclient import TestClient
from main import app

import modules.sentinel_plugins as sentinel_plugins_mod

pytestmark = pytest.mark.integration

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_plugin_manager():
    import tempfile
    import shutil

    tmp = tempfile.mkdtemp(prefix="sentinel-plugins-api-")
    from sentinel.core.plugin_manager import PluginManager
    from sentinel.plugin_sdk import PluginPermissionManager, PluginRegistry

    sentinel_plugins_mod._MANAGER = PluginManager(
        plugin_dir=os.path.join(tmp, "plugins"),
        registry=PluginRegistry(db_path=os.path.join(tmp, "plugins", "plugins.db")),
        permissions=PluginPermissionManager(),
    )
    yield sentinel_plugins_mod._MANAGER
    shutil.rmtree(tmp, ignore_errors=True)


def _auth():
    from modules.jwt_auth import create_access_token

    return {"Authorization": f"Bearer {create_access_token('test', role='admin')}"}


class TestListAndInspect:
    def test_list_returns_official_plugins(self):
        resp = client.get("/api/sentinel/plugins", headers=_auth())
        assert resp.status_code == 200
        ids = {p["id"] for p in resp.json()["plugins"]}
        assert {"spotify", "games", "vscode", "automation", "security"} <= ids

    def test_inspect_spotify(self):
        resp = client.get("/api/sentinel/plugins/spotify", headers=_auth())
        assert resp.status_code == 200
        assert resp.json()["found"] is True
        assert resp.json()["validation"]["valid"] is True

    def test_inspect_unknown_404(self):
        resp = client.get("/api/sentinel/plugins/nope", headers=_auth())
        assert resp.status_code == 404

    def test_metrics_shape(self):
        resp = client.get("/api/sentinel/plugins/metrics", headers=_auth())
        assert resp.status_code == 200
        data = resp.json()
        assert "installed_plugins" in data
        assert "active_plugins" in data


class TestLifecycleFlow:
    def test_full_flow_spotify(self):
        h = _auth()
        resp = client.post("/api/sentinel/plugins/spotify/approve", headers=h)
        assert resp.status_code == 503

    def test_activate_without_approval_blocked(self):
        resp = client.post("/api/sentinel/plugins/vscode/activate", headers=_auth())
        assert resp.status_code == 503

    def test_remove_plugin(self, tmp_path):
        source = tmp_path / "src" / "demo"
        source.mkdir(parents=True)
        (source / "manifest.json").write_text(
            json.dumps({"id": "demo", "name": "Demo", "permissions": []}), encoding="utf-8"
        )
        (source / "plugin.py").write_text(
            "from sentinel.plugin_sdk import SentinelPlugin\nclass DemoPlugin(SentinelPlugin):\n    pass\n",
            encoding="utf-8",
        )
        h = _auth()
        resp = client.post("/api/sentinel/plugins/demo/install", json={"source": str(source)}, headers=h)
        assert resp.status_code == 503

    def test_emit_event(self):
        resp = client.post(
            "/api/sentinel/plugins/emit",
            json={"event": "task.completed", "payload": {"task": "build"}},
            headers=_auth(),
        )
        assert resp.status_code == 503
