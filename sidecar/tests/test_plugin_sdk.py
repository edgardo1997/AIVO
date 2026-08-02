"""Tests for the Sentinel Plugin SDK (FASE 9)."""

import json
import os
import sys
import time

import pytest

from sentinel.plugin_sdk import (
    STATE_ACTIVE,
    STATE_ERROR,
    STATE_INSTALLED,
    STATE_PERMISSION_REVIEW,
    STATE_VALIDATED,
    LifecycleError,
    PERMISSION_CATALOG,
    PermissionDeniedError,
    PermissionToken,
    PluginContext,
    PluginEvent,
    PluginEventBus,
    PluginLifecycle,
    PluginManifest,
    PluginPermissionManager,
    PluginRecord,
    PluginRegistry,
    SentinelPlugin,
    UnknownEventError,
    calculate_checksum,
    evaluate_risk,
    load_manifest,
    requires_user_approval,
    unknown_permissions,
    validate_plugin,
)

pytestmark = pytest.mark.unit


class TestManifest:
    def test_valid_manifest(self):
        manifest = PluginManifest(id="spotify", name="Spotify", version="1.0.0")
        assert manifest.validate() == []

    def test_invalid_id(self):
        assert PluginManifest(id="Uppercase", name="x").validate()

    def test_invalid_version(self):
        assert PluginManifest(id="abc", name="x", version="not-semver").validate()

    def test_missing_name(self):
        assert PluginManifest(id="abc", name="").validate()

    def test_unknown_capability(self):
        assert PluginManifest(id="abc", name="x", capabilities=["hacking"]).validate()

    def test_unknown_event(self):
        assert PluginManifest(id="abc", name="x", events=["not.an.event"]).validate()

    def test_roundtrip_dict(self):
        manifest = PluginManifest(id="spotify", name="Spotify", version="1.0.0", permissions=["application.control"])
        restored = PluginManifest.from_dict(manifest.to_dict())
        assert restored.id == "spotify"
        assert restored.permissions == ["application.control"]

    def test_load_manifest_from_dir(self, tmp_path):
        (tmp_path / "manifest.json").write_text(json.dumps({"id": "demo", "name": "Demo"}), encoding="utf-8")
        assert load_manifest(tmp_path).id == "demo"


class TestPermissions:
    def test_catalog_risk_levels(self):
        assert PERMISSION_CATALOG["process.manage"]["risk"] == "critical"
        assert PERMISSION_CATALOG["filesystem.read"]["risk"] == "low"

    def test_evaluate_risk_highest_wins(self):
        assert evaluate_risk(["filesystem.read", "process.manage"]) == "critical"

    def test_requires_approval_for_medium_plus(self):
        assert requires_user_approval(["system.read"]) is False
        assert requires_user_approval(["application.launch"]) is True

    def test_unknown_permissions(self):
        assert unknown_permissions(["filesystem.read", "totally.fake"]) == ["totally.fake"]

    def test_grant_and_token(self, tmp_path):
        mgr = PluginPermissionManager(clock=lambda: 1000.0)
        token = mgr.grant("demo", ["filesystem.read"], ttl_seconds=3600, now=1000.0)
        assert isinstance(token, PermissionToken)
        assert mgr.has_permission("demo", "filesystem.read", now=1000.0)
        assert not mgr.has_permission("demo", "process.manage", now=1000.0)

    def test_token_expiry(self):
        mgr = PluginPermissionManager(clock=lambda: 1000.0)
        mgr.grant("demo", ["system.read"], ttl_seconds=3600, now=1000.0)
        assert mgr.token_for("demo", now=1000.0) is not None
        assert mgr.token_for("demo", now=9999.0) is None

    def test_revoke(self):
        mgr = PluginPermissionManager(clock=lambda: 1000.0)
        mgr.grant("demo", ["system.read"], now=1000.0)
        assert mgr.revoke("demo")
        assert mgr.token_for("demo", now=1000.0) is None

    def test_require_permission_denied(self):
        mgr = PluginPermissionManager(clock=lambda: 1000.0)
        with pytest.raises(PermissionDeniedError):
            mgr.require_permission("demo", "system.read", now=1000.0)

    def test_context_require(self):
        mgr = PluginPermissionManager(clock=lambda: 1000.0)
        manifest = PluginManifest(id="demo", name="Demo")
        ctx = PluginContext("demo", manifest, mgr)
        with pytest.raises(PermissionDeniedError):
            ctx.require("system.read")
        mgr.grant("demo", ["system.read"], now=1000.0)
        ctx.require("system.read")

    def test_persistence(self, tmp_path):
        from sidecar.repositories.database import DatabaseManager

        storage = DatabaseManager()
        mgr = PluginPermissionManager(storage=storage, clock=lambda: 1000.0)
        mgr.grant("demo", ["system.read"], now=1000.0)
        restored = PluginPermissionManager(storage=storage, clock=lambda: 1000.0)
        assert restored.has_permission("demo", "system.read", now=1000.0)

    def test_grant_rolls_back_when_persistence_fails(self):
        class FailingStorage:
            def config_get_json(self, _key, default):
                return default

            def config_set_json(self, _key, _value):
                raise OSError("disk unavailable")

        mgr = PluginPermissionManager(storage=FailingStorage(), clock=lambda: 1000.0)
        with pytest.raises(RuntimeError, match="Failed to persist"):
            mgr.grant("demo", ["system.read"], now=1000.0)
        assert mgr.token_for("demo", now=1000.0) is None
        assert mgr.approvals() == []

    def test_revoke_rolls_back_when_persistence_fails(self):
        class ToggleStorage:
            def __init__(self):
                self.fail_writes = False

            def config_get_json(self, _key, default):
                return default

            def config_set_json(self, _key, _value):
                if self.fail_writes:
                    raise OSError("disk unavailable")

        storage = ToggleStorage()
        mgr = PluginPermissionManager(storage=storage, clock=lambda: 1000.0)
        mgr.grant("demo", ["system.read"], now=1000.0)
        storage.fail_writes = True
        with pytest.raises(RuntimeError, match="Failed to persist"):
            mgr.revoke("demo")
        assert mgr.has_permission("demo", "system.read", now=1000.0)


class TestLifecycle:
    def test_initial_state(self):
        assert PluginLifecycle().state == STATE_INSTALLED

    def test_happy_path_transitions(self):
        lc = PluginLifecycle()
        lc.transition(STATE_VALIDATED)
        lc.transition(STATE_PERMISSION_REVIEW)
        lc.transition(STATE_ACTIVE)
        assert lc.state == STATE_ACTIVE

    def test_cannot_skip_gate(self):
        lc = PluginLifecycle()
        with pytest.raises(LifecycleError):
            lc.transition(STATE_ACTIVE)

    def test_unknown_state(self):
        lc = PluginLifecycle()
        with pytest.raises(LifecycleError):
            lc.transition("banana")

    def test_can_and_error_recovery(self):
        lc = PluginLifecycle()
        assert lc.can(STATE_VALIDATED)
        assert not lc.can(STATE_ACTIVE)
        lc.transition(STATE_ERROR)
        lc.transition(STATE_INSTALLED)
        assert lc.state == STATE_INSTALLED


class TestEvents:
    def test_subscribe_and_emit(self):
        bus = PluginEventBus(clock=lambda: 100.0)
        seen = []

        def handler(event_dict):
            seen.append(event_dict)
            return "ok"

        bus.subscribe("task.completed", handler)
        results = bus.emit("task.completed", {"task": "build"}, source="sentinel")
        assert results[0]["ok"] is True
        assert seen[0]["type"] == "task.completed"
        assert seen[0]["payload"]["task"] == "build"

    def test_unknown_event_rejected(self):
        bus = PluginEventBus()
        with pytest.raises(UnknownEventError):
            bus.emit("not.known")

    def test_handler_error_isolated(self):
        bus = PluginEventBus()

        def boom(event_dict):
            raise RuntimeError("exploded")

        bus.subscribe("system.warning", boom)
        results = bus.emit("system.warning", {})
        assert results[0]["ok"] is False
        assert "exploded" in results[0]["error"]

    def test_history(self):
        bus = PluginEventBus(clock=lambda: 100.0)
        bus.emit("user.login", {})
        assert len(bus.history()) == 1

    def test_plugin_event_to_dict(self):
        event = PluginEvent(type="game.started", payload={"game": "CS2"}, source="games")
        data = event.to_dict()
        assert data["type"] == "game.started"
        assert data["source"] == "games"


class TestValidator:
    def _make_plugin(self, root, code='from sentinel.plugin_sdk import SentinelPlugin\nclass DemoPlugin(SentinelPlugin):\n    pass\n'):
        (root / "manifest.json").write_text(
            json.dumps({"id": "demo", "name": "Demo", "version": "1.0.0", "permissions": []}),
            encoding="utf-8",
        )
        (root / "plugin.py").write_text(code, encoding="utf-8")
        return root

    def test_valid_plugin(self, tmp_path):
        result = validate_plugin(self._make_plugin(tmp_path))
        assert result["valid"] is True
        assert result["info"]["files"] == 2

    def test_missing_manifest(self, tmp_path):
        result = validate_plugin(tmp_path)
        assert result["valid"] is False
        assert "manifest.json" in result["issues"][0]

    def test_forbidden_core_import(self, tmp_path):
        code = "from sentinel.core.orchestrator import Orchestrator\n"
        result = validate_plugin(self._make_plugin(tmp_path, code=code))
        assert result["valid"] is False
        assert any("forbidden import" in issue for issue in result["issues"])

    def test_unknown_permission_issue(self, tmp_path):
        (tmp_path / "manifest.json").write_text(
            json.dumps({"id": "demo", "name": "Demo", "permissions": ["not.real"]}),
            encoding="utf-8",
        )
        (tmp_path / "plugin.py").write_text("pass", encoding="utf-8")
        result = validate_plugin(tmp_path)
        assert result["valid"] is False

    def test_missing_entrypoint(self, tmp_path):
        (tmp_path / "manifest.json").write_text(
            json.dumps({"id": "demo", "name": "Demo"}), encoding="utf-8"
        )
        result = validate_plugin(tmp_path)
        assert result["valid"] is False

    def test_risky_import_warning(self, tmp_path):
        code = "import os\nos.system('calc')\nclass DemoPlugin:\n    pass\n"
        result = validate_plugin(self._make_plugin(tmp_path, code=code))
        assert result["valid"] is True
        assert any("os.system" in w for w in result["warnings"])

    def test_checksum_stability(self, tmp_path):
        self._make_plugin(tmp_path)
        first, _ = calculate_checksum(tmp_path)
        (tmp_path / "extra.txt").write_text("data", encoding="utf-8")
        second, count = calculate_checksum(tmp_path)
        assert first != second
        assert count == 3


class TestRegistry:
    def test_upsert_get_list_remove(self, tmp_path):
        reg = PluginRegistry(db_path=str(tmp_path / "plugins.db"))
        record = PluginRecord(plugin_id="demo", name="Demo", version="1.0.0", status=STATE_INSTALLED)
        reg.upsert(record)
        assert reg.get("demo").name == "Demo"
        assert [r.plugin_id for r in reg.list()] == ["demo"]
        assert reg.remove("demo")
        assert reg.get("demo") is None

    def test_touch_execution_metrics(self, tmp_path):
        reg = PluginRegistry(db_path=str(tmp_path / "plugins.db"))
        reg.upsert(PluginRecord(plugin_id="demo", name="Demo"))
        reg.touch_execution("demo", ok=True, duration_ms=42.0, detail="command:saludo")
        reg.touch_execution("demo", ok=False, duration_ms=10.0, detail="command:saludo")
        agg = reg.aggregate_metrics("demo")
        assert agg["calls"] == 2
        assert agg["failures"] == 1
        record = reg.get("demo")
        assert record.failure_count == 1

    def test_set_trust_and_approval(self, tmp_path):
        reg = PluginRegistry(db_path=str(tmp_path / "plugins.db"))
        reg.upsert(PluginRecord(plugin_id="demo", name="Demo"))
        reg.set_trust("demo", 90.0, "official")
        reg.set_approval("demo", "approved")
        record = reg.get("demo")
        assert record.trust_score == 90.0
        assert record.certification == "official"
        assert record.approval_status == "approved"


class TestPluginBase:
    def test_context_permissions_property(self):
        mgr = PluginPermissionManager(clock=lambda: 100.0)
        mgr.grant("demo", ["system.read"], now=100.0)
        ctx = PluginContext("demo", PluginManifest(id="demo", name="Demo"), mgr)
        assert ctx.permissions == ["system.read"]

    def test_context_has(self):
        mgr = PluginPermissionManager(clock=lambda: 100.0)
        mgr.grant("demo", ["system.read"], now=100.0)
        ctx = PluginContext("demo", PluginManifest(id="demo", name="Demo"), mgr)
        assert ctx.has("system.read")
        assert not ctx.has("process.manage")

    def test_emit_through_context(self):
        bus = PluginEventBus(clock=lambda: 100.0)
        seen = []

        def handler(event_dict):
            seen.append(event_dict)

        bus.subscribe("game.started", handler)
        ctx = PluginContext(
            "games",
            PluginManifest(id="games", name="Games"),
            PluginPermissionManager(clock=lambda: 100.0),
            emit_event=lambda ev: bus.emit(ev.type, ev.payload, source=ev.source),
        )
        ctx.emit("game.started", {"game": "CS2"})
        assert seen and seen[0]["payload"]["game"] == "CS2"

    def test_plugin_default_handlers(self):
        plugin = SentinelPlugin()
        assert plugin.on_ready()["status"] == "ready"
        assert plugin.on_command("anything")["handled"] is False

    def test_plugin_require_uses_context(self):
        mgr = PluginPermissionManager(clock=lambda: 100.0)
        mgr.grant("demo", ["system.read"], now=100.0)
        ctx = PluginContext("demo", PluginManifest(id="demo", name="Demo"), mgr)
        plugin = SentinelPlugin(ctx)
        plugin.require("system.read")
        with pytest.raises(PermissionDeniedError):
            plugin.require("process.manage")
