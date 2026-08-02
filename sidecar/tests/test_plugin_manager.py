"""Tests for the PluginManager orchestration layer (FASE 9)."""

import json
import os

import pytest

from sentinel.core.plugin_manager import (
    DEFAULT_PLUGIN_DIR,
    OFFICIAL_PLUGINS_DIR,
    PluginManager,
    TRUST_CERTIFICATIONS,
)
from sentinel.plugin_sdk import (
    STATE_ACTIVE,
    STATE_DEACTIVATED,
    STATE_ERROR,
    STATE_INSTALLED,
    STATE_PERMISSION_REVIEW,
    STATE_VALIDATED,
    PluginPermissionManager,
    PluginRegistry,
    SentinelPlugin,
)

pytestmark = pytest.mark.unit

GOOD_MANIFEST = {
    "id": "echo",
    "name": "Echo Plugin",
    "version": "1.0.0",
    "description": "echoes commands",
    "permissions": ["system.read"],
}

ECHO_CODE = '''\
from sentinel.plugin_sdk import SentinelPlugin


class EchoPlugin(SentinelPlugin):
    def on_ready(self):
        return {"status": "ready"}

    def on_command(self, command, **kwargs):
        return {"handled": True, "echo": str(command)}

    def on_event(self, event):
        return {"handled": event.type}
'''


def _write_plugin(root, plugin_id, manifest=None, code=ECHO_CODE):
    plugin_dir = root / plugin_id
    plugin_dir.mkdir(parents=True, exist_ok=True)
    data = dict(GOOD_MANIFEST)
    data["id"] = plugin_id
    data["name"] = (manifest or {}).get("name") or plugin_id.title()
    if manifest:
        data.update(manifest)
    (plugin_dir / "manifest.json").write_text(json.dumps(data), encoding="utf-8")
    (plugin_dir / "plugin.py").write_text(code, encoding="utf-8")
    return plugin_dir


@pytest.fixture
def manager(tmp_path):
    return PluginManager(
        plugin_dir=str(tmp_path / "plugins"),
        registry=PluginRegistry(db_path=str(tmp_path / "plugins" / "plugins.db")),
        permissions=PluginPermissionManager(clock=lambda: 1000.0),
    )


class TestManagerDiscovery:
    def test_discover_includes_official(self, manager):
        ids = {p["id"] for p in manager.discover()}
        assert {"spotify", "games", "vscode", "automation", "security"} <= ids

    def test_discover_new_plugin(self, manager, tmp_path):
        _write_plugin(tmp_path / "src", "echo")
        manager.install(str(tmp_path / "src" / "echo"))
        ids = {p["id"] for p in manager.discover()}
        assert "echo" in ids

    def test_list_fields(self, manager, tmp_path):
        _write_plugin(tmp_path / "src", "echo")
        manager.install(str(tmp_path / "src" / "echo"))
        item = [p for p in manager.list() if p["id"] == "echo"][0]
        assert item["name"] == "Echo"
        assert item["status"] == STATE_INSTALLED
        assert item["certification"] == "verified"

    def test_official_dir_is_real(self):
        assert os.path.isdir(OFFICIAL_PLUGINS_DIR)
        assert os.path.isdir(os.path.join(OFFICIAL_PLUGINS_DIR, "spotify"))
        assert os.path.isdir(os.path.join(OFFICIAL_PLUGINS_DIR, "games"))
        assert os.path.isdir(os.path.join(OFFICIAL_PLUGINS_DIR, "vscode"))
        assert os.path.isdir(os.path.join(OFFICIAL_PLUGINS_DIR, "automation"))
        assert os.path.isdir(os.path.join(OFFICIAL_PLUGINS_DIR, "security"))

    def test_official_plugins_are_discovered_and_valid(self, manager):
        for plugin in manager.discover():
            if plugin.get("official"):
                inspection = manager.inspect(plugin["id"])
                assert inspection["validation"]["valid"], inspection["validation"]["issues"]


class TestManagerInstallValidate:
    def test_install_success(self, manager, tmp_path):
        _write_plugin(tmp_path / "src", "echo")
        result = manager.install(str(tmp_path / "src" / "echo"))
        assert result["success"] is True
        assert result["id"] == "echo"
        assert result["checksum_sha256"]
        assert manager.inspect("echo")["found"] is True

    def test_install_rejects_missing_dir(self, manager):
        result = manager.install(str(os.path.join(os.environ.get("TEMP", ""), "no-such-dir")))
        assert result["success"] is False

    def test_install_duplicate(self, manager, tmp_path):
        _write_plugin(tmp_path / "src", "echo")
        manager.install(str(tmp_path / "src" / "echo"))
        result = manager.install(str(tmp_path / "src" / "echo"))
        assert result["success"] is False

    def test_install_rejects_invalid(self, manager, tmp_path):
        bad = tmp_path / "src" / "bad"
        bad.mkdir(parents=True)
        (bad / "manifest.json").write_text(json.dumps({"id": "bad", "name": "Bad", "permissions": ["fake.perm"]}), encoding="utf-8")
        (bad / "plugin.py").write_text("pass", encoding="utf-8")
        result = manager.install(str(bad))
        assert result["success"] is False

    def test_validate_sets_lifecycle(self, manager, tmp_path):
        _write_plugin(tmp_path / "src", "echo")
        manager.install(str(tmp_path / "src" / "echo"))
        result = manager.validate("echo")
        assert result["success"] is True
        assert result["state"] == STATE_VALIDATED


class TestManagerPermissionGate:
    def test_activate_blocked_without_token(self, manager, tmp_path):
        _write_plugin(tmp_path / "src", "echo")
        manager.install(str(tmp_path / "src" / "echo"))
        result = manager.activate("echo")
        assert result["success"] is False
        assert result["blocked"] == STATE_PERMISSION_REVIEW
        assert result["missing"] == ["system.read"]
        echo = [p for p in manager.list() if p["id"] == "echo"][0]
        assert echo["status"] == STATE_PERMISSION_REVIEW

    def test_approve_then_activate(self, manager, tmp_path):
        _write_plugin(tmp_path / "src", "echo")
        manager.install(str(tmp_path / "src" / "echo"))
        approval = manager.approve_permissions("echo")
        assert approval["success"] is True
        assert approval["token"]["plugin_id"] == "echo"
        result = manager.activate("echo")
        assert result["success"] is True
        assert result["state"] == STATE_ACTIVE

    def test_approve_cannot_grant_undeclared(self, manager, tmp_path):
        _write_plugin(tmp_path / "src", "echo")
        manager.install(str(tmp_path / "src" / "echo"))
        result = manager.approve_permissions("echo", permissions=["process.manage"])
        assert result["success"] is False

    def test_dispatch_command_after_activation(self, manager, tmp_path):
        _write_plugin(tmp_path / "src", "echo")
        manager.install(str(tmp_path / "src" / "echo"))
        manager.approve_permissions("echo")
        manager.activate("echo")
        result = manager.dispatch_command("echo", "saludo")
        assert result["handled"] is True
        assert result["result"]["echo"] == "saludo"

    def test_dispatch_inactive_plugin(self, manager):
        result = manager.dispatch_command("echo", "saludo")
        assert result["handled"] is False

    def test_deactivate(self, manager, tmp_path):
        _write_plugin(tmp_path / "src", "echo")
        manager.install(str(tmp_path / "src" / "echo"))
        manager.approve_permissions("echo")
        manager.activate("echo")
        result = manager.deactivate("echo")
        assert result["success"] is True
        assert result["state"] == STATE_DEACTIVATED
        echo = [p for p in manager.list() if p["id"] == "echo"][0]
        assert echo["status"] == STATE_DEACTIVATED


class TestManagerEvents:
    def test_emit_delivers_to_subscriber(self, manager, tmp_path):
        event_code = '''\
from sentinel.plugin_sdk import SentinelPlugin


class EchoPlugin(SentinelPlugin):
    def on_ready(self):
        return {"status": "ready"}

    def on_event(self, event):
        return {"handled": True, "task": event.payload.get("task")}
'''
        _write_plugin(tmp_path / "src", "echo", manifest={"events": ["task.completed"]}, code=event_code)
        manager.install(str(tmp_path / "src" / "echo"))
        manager.approve_permissions("echo")
        manager.activate("echo")
        results = manager.emit("task.completed", {"task": "build"})
        assert any(r["ok"] for r in results)
        assert results[0]["result"]["result"]["task"] == "build"

    def test_emit_unknown_event_rejected(self, manager):
        with pytest.raises(Exception):
            manager.emit("not.an.event")

    def test_emit_to_unsubscribed_is_empty(self, manager, tmp_path):
        _write_plugin(tmp_path / "src", "echo")
        manager.install(str(tmp_path / "src" / "echo"))
        manager.approve_permissions("echo")
        manager.activate("echo")
        assert manager.emit("game.started", {}) == []


class TestManagerTrustAndMetrics:
    def test_trust_certification_bounds(self, manager):
        assert manager._certification_for(95) == "official"
        assert manager._certification_for(80) == "trusted"
        assert manager._certification_for(55) == "verified"
        assert manager._certification_for(10) == "community"

    def test_certification_thresholds_ordering(self):
        assert TRUST_CERTIFICATIONS[0][1] > TRUST_CERTIFICATIONS[-1][1]

    def test_metrics_after_activation(self, manager, tmp_path):
        _write_plugin(tmp_path / "src", "echo")
        manager.install(str(tmp_path / "src" / "echo"))
        manager.approve_permissions("echo")
        manager.activate("echo")
        metrics = manager.metrics()
        assert metrics["installed_plugins"] == 1
        assert metrics["active_plugins"] == 1

    def test_metrics_execution_counting(self, manager, tmp_path):
        _write_plugin(tmp_path / "src", "echo")
        manager.install(str(tmp_path / "src" / "echo"))
        manager.approve_permissions("echo")
        manager.activate("echo")
        manager.dispatch_command("echo", "hola")
        metrics = manager.metrics()
        assert metrics["execution"]["calls"] >= 1


class TestManagerRemove:
    def test_remove_plugin(self, manager, tmp_path):
        _write_plugin(tmp_path / "src", "echo")
        manager.install(str(tmp_path / "src" / "echo"))
        result = manager.remove("echo")
        assert result["success"] is True
        assert manager.inspect("echo")["found"] is False

    def test_remove_revokes_token(self, manager, tmp_path):
        _write_plugin(tmp_path / "src", "echo")
        manager.install(str(tmp_path / "src" / "echo"))
        manager.approve_permissions("echo")
        manager.remove("echo")
        assert manager._permissions.token_for("echo") is None

    def test_update_replace(self, manager, tmp_path):
        _write_plugin(tmp_path / "src", "echo")
        manager.install(str(tmp_path / "src" / "echo"))
        assert manager._locate("echo") is not None
        _write_plugin(tmp_path / "src2", "echo")
        result = manager.update("echo", str(tmp_path / "src2" / "echo"))
        assert result["success"] is True
