"""FASE 7 — Production observability: dashboard + diagnostics.

Exercises the REAL ObservabilityEngine wired into the production stack and the
FastAPI endpoints /api/observability/dashboard and /api/observability/diagnostics.
"""

import pytest

from sentinel.observability.engine import ObservabilityConfig, ObservabilityEngine
from tests.production.harness import IDENTITY

pytestmark = pytest.mark.production


class TestDashboardEngine:
    @pytest.mark.asyncio
    async def test_dashboard_returns_real_sections(self, stack):
        dash = stack.observability.get_dashboard()
        for key in ("health", "metrics", "models", "recovery", "alerts", "traces"):
            assert key in dash, f"dashboard missing {key}"
        assert "status" in dash["health"]

    @pytest.mark.asyncio
    async def test_dashboard_reflects_recorded_requests(self, stack):
        stack.observability.record_request("prod-model", True, 15.0)
        dash = stack.observability.get_dashboard()
        models = dash["models"]
        assert "prod-model" in models
        assert models["prod-model"]["requests"] >= 1


class TestDashboardEndpoint:
    def test_endpoint_reachable(self, fastapi_client):
        r = fastapi_client.get("/api/observability/dashboard")
        assert r.status_code == 200
        body = r.json()
        assert body["observability"]["enabled"] is True
        for key in ("health", "metrics", "models", "costs", "network", "plugins", "running_tasks", "recovery", "alerts", "traces", "system"):
            assert key in body, f"dashboard endpoint missing {key}"

    def test_costs_section_is_real(self, fastapi_client):
        body = fastapi_client.get("/api/observability/dashboard").json()
        assert "total_cost_usd" in body["costs"]
        assert "by_model" in body["costs"]


class TestDiagnosticsEndpoint:
    def test_diagnostics_reachable(self, fastapi_client):
        r = fastapi_client.get("/api/observability/diagnostics")
        assert r.status_code == 200
        body = r.json()
        assert "summary" in body
        assert "checks" in body
        names = [c["name"] for c in body["checks"]]
        assert "observability_engine" in names
        assert "database" in names
        for c in body["checks"]:
            assert c["status"] in ("ok", "warn", "fail")

    def test_engine_check_healthy(self, fastapi_client):
        body = fastapi_client.get("/api/observability/diagnostics").json()
        engine_check = next(c for c in body["checks"] if c["name"] == "observability_engine")
        assert engine_check["status"] == "ok"


class TestStandaloneDiagnostics:
    def test_diagnostics_runs_without_app(self):
        from sentinel.observability.diagnostics import run_diagnostics

        engine = ObservabilityEngine(ObservabilityConfig(backup_dir="backup-tmp"))
        data = run_diagnostics(engine, include_system=False)
        assert data["summary"] in ("ok", "warn", "fail")
        names = [c["name"] for c in data["checks"]]
        assert "observability_engine" in names

    def test_diagnostics_reports_missing_engine(self):
        from sentinel.observability.diagnostics import run_diagnostics

        data = run_diagnostics(None, include_system=False)
        engine_check = next(c for c in data["checks"] if c["name"] == "observability_engine")
        assert engine_check["status"] == "fail"
