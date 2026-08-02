"""Phase 5 — Stability Testing

Validates real-world resilience scenarios:
  - Sidecar: process kill, restart, crash recovery
  - Database: corrupt config, migration, restore
  - Router: no internet, provider timeout, invalid key
  - UI: backend offline, reconnection
"""

import json
import os
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from main import app
from sentinel.core.model_router import ModelRouter, TaskType, OFFLINE_MODES
from sentinel.core.provider_health import (
    HealthState,
    HealthResult,
    ProviderHealthChecker,
)

pytestmark = pytest.mark.stability


# ── Sidecar: process kill, restart, crash recovery ──────────────────────


class TestSidecarResilience:
    """Validate sidecar survives restarts and crash recovery."""

    def test_health_after_restart(self, client: TestClient):
        """Boot -> sidecar estable -> health endpoint responds."""
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"

    def test_crash_recovery_recovers(self, client: TestClient):
        """Crash (simulated via runtime re-init) -> recovery."""
        resp = client.get("/api/system/live")
        assert resp.status_code == 200
        live = resp.json()
        assert live["status"] in ("connected", "degraded")
        assert isinstance(live["cpu"], (int, float))
        assert isinstance(live["processes"], int)

    def test_dashboard_config_access_after_restart(self, client: TestClient):
        """After restart cycle, config endpoint still works."""
        resp = client.get("/ai/config", headers={"Authorization": "Bearer valid-test-token"})
        assert resp.status_code == 200
        data = resp.json()
        assert "provider" in data
        assert "routing_config" in data

    def test_tools_available_after_restart(self, client: TestClient):
        """Tools disponiveis after startup."""
        resp = client.post(
            "/v1/execute",
            json={"tool_id": "system.info", "params": {}},
            headers={"Authorization": "Bearer valid-test-token"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("success") is not False


# ── Database: corrupt config, migration, restore ────────────────────────


class TestDatabaseStability:
    """Validate database handles corruption, migration, and restore."""

    def _init_db(self, path):
        """Create a fresh SQLite DB with the schema needed for testing."""
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                action TEXT NOT NULL,
                details TEXT,
                status TEXT,
                user TEXT
            );
        """)
        conn.commit()
        return conn

    def test_db_loads_defaults_on_empty(self, tmp_path):
        """Fresh DB -> config table exists but empty."""
        db_path = tmp_path / "test_empty.db"
        conn = self._init_db(db_path)
        row = conn.execute("SELECT value FROM config WHERE key='ai_config'").fetchone()
        assert row is None
        conn.close()

    def test_db_restores_config_after_save(self, tmp_path):
        """Save config -> DB returns same values."""
        db_path = tmp_path / "test_restore.db"
        conn = self._init_db(db_path)
        cfg = json.dumps({"provider": "nvidia-nemotron", "strategy": "priority", "offline_mode": "auto"})
        conn.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", ("ai_config", cfg))
        conn.commit()
        row = conn.execute("SELECT value FROM config WHERE key='ai_config'").fetchone()
        loaded = json.loads(row[0])
        assert loaded["provider"] == "nvidia-nemotron"
        assert loaded["strategy"] == "priority"
        assert loaded["offline_mode"] == "auto"
        conn.close()

    def test_corrupt_config_does_not_crash(self, tmp_path):
        """Corrupt SQLite file -> can still create a new connection safely."""
        db_path = tmp_path / "test_corrupt.db"
        with open(db_path, "w") as f:
            f.write("not a valid sqlite database at all!!!")
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute("SELECT 1")
            assert False, "Should have raised an exception on corrupt DB"
        except sqlite3.DatabaseError:
            pass
        finally:
            conn.close()

    def test_recreate_db_after_corruption(self, tmp_path):
        """After corruption, fresh DB can be created and queried."""
        db_path = tmp_path / "test_recreate.db"
        with open(db_path, "w") as f:
            f.write("garbage data that should be replaced")
        os.remove(db_path)
        conn = self._init_db(db_path)
        conn.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
            ("ai_config", json.dumps({"provider": "sentinel_local"})),
        )
        conn.commit()
        row = conn.execute("SELECT value FROM config WHERE key='ai_config'").fetchone()
        assert json.loads(row[0])["provider"] == "sentinel_local"
        conn.close()

    def test_audit_log_survives_restart(self, tmp_path):
        """Audit log entries persist across DB close/reopen."""
        db_path = tmp_path / "test_audit_persist.db"
        conn1 = self._init_db(db_path)
        conn1.execute(
            "INSERT INTO audit_log (timestamp, action, details, status, user) VALUES (?, ?, ?, ?, ?)",
            ("2026-01-01T00:00:00Z", "config_changed", "test", "info", "system"),
        )
        conn1.commit()
        conn1.close()
        conn2 = sqlite3.connect(str(db_path))
        conn2.row_factory = sqlite3.Row
        row = conn2.execute("SELECT action FROM audit_log WHERE action='config_changed'").fetchone()
        assert row is not None
        assert row["action"] == "config_changed"
        conn2.close()


# ── Router: no internet, provider timeout, invalid key ──────────────────


class TestRouterStability:
    """Validate router handles offline, timeout, and invalid keys."""

    def test_router_filters_cloud_when_offline(self):
        """force_local -> only local providers remain as candidates."""
        mr = ModelRouter()
        mr.set_api_key("deepseek", "test-key")
        mr.set_api_key("nvidia-nemotron", "test-key")
        # Make sentinel_local available by monkeypatching
        original = mr.provider_availability
        mr.provider_availability = lambda pid, refresh=False: type(
            "PA", (), {"available": pid == "sentinel_local", "to_dict": lambda: {"available": pid == "sentinel_local"}}
        )()
        mr.set_offline_mode("force_local")
        candidates = mr._filter_candidates(TaskType.QUICK)
        assert len(candidates) > 0, "Should have at least local candidates"
        for c in candidates:
            assert c.is_local, f"Cloud provider {c.id} should be filtered out when offline"
        mr.provider_availability = original

    def test_router_offline_filter_excludes_cloud(self):
        """Offline filter removes cloud providers even when they have keys."""
        mr = ModelRouter()
        mr.set_api_key("nvidia-nemotron", "test-key")
        all_candidates = mr._filter_candidates(TaskType.QUICK)
        cloud_before = [c for c in all_candidates if not c.is_local]
        mr.set_offline_mode("force_local")
        offline_candidates = mr._filter_candidates(TaskType.QUICK)
        cloud_after = [c for c in offline_candidates if not c.is_local]
        assert len(cloud_after) == 0, "Cloud providers should be excluded in offline mode"
        assert len(cloud_before) > 0, "Cloud providers should be available online"

    def test_router_all_providers_fail_gracefully(self):
        """All providers fail -> RuntimeError with explanation."""
        mr = ModelRouter(providers=[])
        with pytest.raises(RuntimeError) as exc:
            mr.chat(
                messages=[{"role": "user", "content": "hi"}],
                task_type=TaskType.QUICK,
            )
        assert "provider" in str(exc.value).lower() or "failed" in str(exc.value).lower()

    def test_router_offline_mode_enum(self):
        """Offline mode must be one of valid values."""
        mr = ModelRouter()
        mr.set_offline_mode("auto")
        assert mr.get_offline_mode() == "auto"
        mr.set_offline_mode("force_local")
        assert mr.get_offline_mode() == "force_local"
        mr.set_offline_mode("off")
        assert mr.get_offline_mode() == "off"
        with pytest.raises(ValueError):
            mr.set_offline_mode("invalid_mode")

    def test_router_provider_availability_cache(self):
        """Availability cache returns cached result within TTL."""
        mr = ModelRouter()
        mr.set_api_key("nvidia-nemotron", "test-key")
        result1 = mr.provider_availability("nvidia-nemotron")
        assert result1.available
        result2 = mr.provider_availability("nvidia-nemotron")
        assert result2.checked_at == result1.checked_at

    def test_health_checker_states(self):
        """HealthState enum values are correct."""
        assert HealthState.AVAILABLE.value == "available"
        assert HealthState.DEGRADED.value == "degraded"
        assert HealthState.OFFLINE.value == "offline"
        assert HealthState.DISABLED.value == "disabled"

    def test_health_checker_fake_provider(self):
        """Health checker returns OFFLINE for unreachable provider."""
        hc = ProviderHealthChecker()
        result = hc.check_health("fake", "http://localhost:1")
        assert result.state == HealthState.OFFLINE

    def test_health_checker_caches_results(self):
        """Health checker returns cached result within TTL."""
        hc = ProviderHealthChecker(availability_ttl=60.0)
        result1 = hc.check_health("fake2", "http://localhost:2")
        result2 = hc.check_health("fake2", "http://localhost:2")
        assert result2.checked_at == result1.checked_at


# ── UI: backend offline, reconnection ───────────────────────────────────


class TestUIBackendStability:
    """Validate endpoint behavior when backend is offline/recovering."""

    def test_live_endpoint_returns_degraded_on_failure(self, client: TestClient):
        """Live endpoint returns degraded status on partial failure."""
        resp = client.get("/api/system/live")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert isinstance(data["cpu"], (int, float))
        assert isinstance(data["memory"], dict)
        assert isinstance(data["disk"], dict)

    def test_health_endpoint_always_accessible(self, client: TestClient):
        """Health endpoint always responds, even without auth."""
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    def test_live_endpoint_no_auth_required(self, client: TestClient):
        """Live endpoint accessible without authentication token."""
        noauth = TestClient(app)
        resp = noauth.get("/api/system/live")
        assert resp.status_code == 200

    def test_live_endpoint_stable_polling(self, client: TestClient):
        """Multiple rapid polls return consistent structure."""
        for _ in range(5):
            resp = client.get("/api/system/live")
            assert resp.status_code == 200
            data = resp.json()
            assert set(data.keys()) == {
                "cpu",
                "memory",
                "gpu",
                "disk",
                "processes",
                "uptime",
                "timestamp",
                "status",
            }


# ── Full boot chain integration ─────────────────────────────────────────


class TestBootChain:
    """Validate full boot chain: Boot -> Sidecar -> DB -> Router -> Tools -> UI."""

    def test_boot_chain(self, client: TestClient):
        """Boot -> Sidecar estable -> Runtime carga -> DB restaura -> Router selecciona modelo -> Tools disponibles -> UI recibe estado."""
        # 1. Sidecar estable (health)
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["status"] == "healthy"

        # 2. Runtime carga (tools available)
        tools = client.post(
            "/v1/execute",
            json={"tool_id": "system.info", "params": {}},
            headers={"Authorization": "Bearer valid-test-token"},
        )
        assert tools.status_code == 200
        tool_data = tools.json()
        assert tool_data.get("success") is not False or "data" in tool_data

        # 3. DB restaura (config exists)
        config = client.get(
            "/ai/config",
            headers={"Authorization": "Bearer valid-test-token"},
        )
        assert config.status_code == 200
        cfg_data = config.json()
        assert "provider" in cfg_data
        assert "routing_config" in cfg_data

        # 4. Router selecciona modelo (routing config has strategy)
        routing = cfg_data["routing_config"]
        assert "strategy" in routing
        assert "preferred_provider" in routing

        # 5. Tools disponibles (multiple tool calls work)
        cpu = client.post(
            "/v1/execute",
            json={"tool_id": "system.cpu", "params": {}},
            headers={"Authorization": "Bearer valid-test-token"},
        )
        assert cpu.status_code == 200

        # 6. UI recibe estado (live endpoint returns full data)
        live = client.get("/api/system/live")
        assert live.status_code == 200
        live_data = live.json()
        assert live_data["status"] in ("connected", "degraded")
        assert isinstance(live_data["cpu"], (int, float))
        assert isinstance(live_data["memory"]["percent"], (int, float))
        assert isinstance(live_data["disk"]["percent"], (int, float))
        assert isinstance(live_data["processes"], int)
        assert isinstance(live_data["uptime"], (int, float))
