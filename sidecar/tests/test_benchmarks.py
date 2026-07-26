import os

"""Performance benchmarks for critical Sentinel pipeline paths.

Run: pytest sidecar/tests/test_benchmarks.py --benchmark-only
Compare: pytest-benchmarks sidecar/tests/test_benchmarks.py --benchmark-compare=0001
"""
import asyncio
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from main import app, _rate_limiter
from modules.permissions import _svc as perm_svc

pytestmark = pytest.mark.performance

client = TestClient(app)

# ── Performance budgets (milliseconds) ─────────────────────────────────────
# These thresholds catch regressions in CI. Tune if the environment is
# consistently slower/faster.
BUDGET_PIPELINE_FAST_MS = 2000  # single-step process (e.g., cpu)
BUDGET_PIPELINE_MULTI_MS = 5000  # multi-step process (e.g., system health)
BUDGET_EXECUTE_MS = 2000  # direct v1/execute calls
BUDGET_API_READ_MS = 1000  # simple read-only API endpoints
BUDGET_API_HEAVY_MS = 2000  # heavier read endpoints (hardening health)
BUDGET_CONTEXT_NO_PROC_MS = 2000  # context engine without processes
BUDGET_CONTEXT_WITH_PROC_MS = 12000  # context engine with processes (psutil)
BUDGET_DB_MS = 500  # database operations
BUDGET_MEMORY_MS = 200  # operational memory operations


@pytest.fixture(scope="module", autouse=True)
def benchmark_configuration():
    """Keep benchmark-only mutations isolated from the regression suite."""
    original_allow = _rate_limiter.allow
    perm_svc.set_level("admin")
    _rate_limiter.allow = lambda key, limit=999999: type(  # noqa: ARG005
        "_", (), {"allowed": True, "remaining": 999, "retry_after": 0}
    )()
    yield
    _rate_limiter.allow = original_allow
    perm_svc.set_level("confirm")


@pytest.fixture(scope="module", autouse=True)
def warmup(benchmark_configuration):
    """Warm up the orchestrator singleton (first-call latency is high)."""
    _rate_limiter.clear()
    client.post("/api/sentinel/process", json={"utterance": "cpu usage"})
    client.post("/v1/execute", json={"tool_id": "system.cpu", "params": {}})


class TestPipelineBenchmarks:
    """Benchmarks for the core orchestrator pipeline."""

    def test_process_cpu(self, benchmark):
        resp = benchmark(client.post, "/api/sentinel/process", json={"utterance": "cpu usage"})
        assert resp.status_code == 200
        max_ms = benchmark.stats.stats.max * 1000
        assert max_ms < BUDGET_PIPELINE_FAST_MS, f"process/cpu took {max_ms:.0f}ms (budget {BUDGET_PIPELINE_FAST_MS}ms)"

    def test_process_system_health_multi_step(self, benchmark):
        resp = benchmark(client.post, "/api/sentinel/process", json={"utterance": "analyze system health"})
        assert resp.status_code == 200
        max_ms = benchmark.stats.stats.max * 1000
        assert max_ms < BUDGET_PIPELINE_MULTI_MS, (
            f"process/system_health took {max_ms:.0f}ms (budget {BUDGET_PIPELINE_MULTI_MS}ms)"
        )

    def test_dry_run_skip_simulation(self, benchmark):
        resp = benchmark(
            client.post,
            "/api/sentinel/process",
            json={
                "utterance": "cpu usage",
                "dry_run": True,
            },
        )
        assert resp.status_code == 200
        max_ms = benchmark.stats.stats.max * 1000
        assert max_ms < BUDGET_PIPELINE_FAST_MS, (
            f"process/dry_run took {max_ms:.0f}ms (budget {BUDGET_PIPELINE_FAST_MS}ms)"
        )

    def test_v1_execute_cpu(self, benchmark):
        resp = benchmark(client.post, "/v1/execute", json={"tool_id": "system.cpu", "params": {}})
        assert resp.status_code == 200
        max_ms = benchmark.stats.stats.max * 1000
        assert max_ms < BUDGET_EXECUTE_MS, f"execute/cpu took {max_ms:.0f}ms (budget {BUDGET_EXECUTE_MS}ms)"

    def test_v1_execute_system_info(self, benchmark):
        resp = benchmark(client.post, "/v1/execute", json={"tool_id": "system.info", "params": {}})
        assert resp.status_code == 200
        max_ms = benchmark.stats.stats.max * 1000
        assert max_ms < BUDGET_EXECUTE_MS, f"execute/system_info took {max_ms:.0f}ms (budget {BUDGET_EXECUTE_MS}ms)"

    def test_v1_execute_app_discovery(self, benchmark):
        resp = benchmark(
            client.post,
            "/v1/execute",
            json={
                "tool_id": "app.discovery",
                "params": {"action": "list"},
            },
        )
        assert resp.status_code == 200
        max_ms = benchmark.stats.stats.max * 1000
        assert max_ms < BUDGET_EXECUTE_MS, f"execute/app_discovery took {max_ms:.0f}ms (budget {BUDGET_EXECUTE_MS}ms)"


class TestApiEndpointBenchmarks:
    """Benchmarks for read-only API endpoints."""

    def test_health(self, benchmark):
        resp = benchmark(client.get, "/api/health")
        assert resp.status_code == 200
        max_ms = benchmark.stats.stats.max * 1000
        assert max_ms < BUDGET_API_READ_MS, f"health took {max_ms:.0f}ms (budget {BUDGET_API_READ_MS}ms)"

    def test_capabilities(self, benchmark):
        resp = benchmark(client.get, "/api/sentinel/capabilities")
        assert resp.status_code == 200
        max_ms = benchmark.stats.stats.max * 1000
        assert max_ms < BUDGET_API_READ_MS, f"capabilities took {max_ms:.0f}ms (budget {BUDGET_API_READ_MS}ms)"

    def test_goals(self, benchmark):
        resp = benchmark(client.get, "/api/sentinel/goals")
        assert resp.status_code == 200
        max_ms = benchmark.stats.stats.max * 1000
        assert max_ms < BUDGET_API_READ_MS, f"goals took {max_ms:.0f}ms (budget {BUDGET_API_READ_MS}ms)"

    def test_audit(self, benchmark):
        resp = benchmark(client.get, "/v1/audit?limit=10")
        assert resp.status_code == 200
        max_ms = benchmark.stats.stats.max * 1000
        assert max_ms < BUDGET_API_READ_MS, f"audit took {max_ms:.0f}ms (budget {BUDGET_API_READ_MS}ms)"

    def test_agents_list(self, benchmark):
        resp = benchmark(client.get, "/v1/agents")
        assert resp.status_code == 200
        max_ms = benchmark.stats.stats.max * 1000
        assert max_ms < BUDGET_API_READ_MS, f"agents took {max_ms:.0f}ms (budget {BUDGET_API_READ_MS}ms)"

    def test_triggers_list(self, benchmark):
        resp = benchmark(client.get, "/v1/triggers")
        assert resp.status_code == 200
        max_ms = benchmark.stats.stats.max * 1000
        assert max_ms < BUDGET_API_READ_MS, f"triggers took {max_ms:.0f}ms (budget {BUDGET_API_READ_MS}ms)"

    def test_hardening_config(self, benchmark):
        resp = benchmark(client.get, "/api/sentinel/hardening/config")
        assert resp.status_code == 200
        max_ms = benchmark.stats.stats.max * 1000
        assert max_ms < BUDGET_API_READ_MS, f"hardening/config took {max_ms:.0f}ms (budget {BUDGET_API_READ_MS}ms)"

    def test_hardening_health(self, benchmark):
        resp = benchmark(client.get, "/api/sentinel/hardening/health")
        assert resp.status_code == 200
        max_ms = benchmark.stats.stats.max * 1000
        assert max_ms < BUDGET_API_HEAVY_MS, f"hardening/health took {max_ms:.0f}ms (budget {BUDGET_API_HEAVY_MS}ms)"

    def test_info(self, benchmark):
        resp = benchmark(client.get, "/api/info")
        assert resp.status_code == 200
        max_ms = benchmark.stats.stats.max * 1000
        assert max_ms < BUDGET_API_READ_MS, f"info took {max_ms:.0f}ms (budget {BUDGET_API_READ_MS}ms)"

    def test_profile(self, benchmark):
        resp = benchmark(client.get, "/v1/profile")
        assert resp.status_code == 200
        max_ms = benchmark.stats.stats.max * 1000
        assert max_ms < BUDGET_API_READ_MS, f"profile took {max_ms:.0f}ms (budget {BUDGET_API_READ_MS}ms)"

    def test_vault_status(self, benchmark):
        resp = benchmark(client.get, "/api/sentinel/vault/status")
        assert resp.status_code == 200
        max_ms = benchmark.stats.stats.max * 1000
        assert max_ms < BUDGET_API_READ_MS, f"vault/status took {max_ms:.0f}ms (budget {BUDGET_API_READ_MS}ms)"


class TestContextEngineBenchmarks:
    """Benchmarks for the context engine (psutil calls)."""

    def test_context_collect_no_processes(self, benchmark):
        from sentinel.core.context import ContextEngine

        engine = ContextEngine(collect_processes=False)

        def run():
            return asyncio.run(engine.collect(include_processes=False))

        result = benchmark(run)
        assert result.cpu.get("percent") is not None
        max_ms = benchmark.stats.stats.max * 1000
        assert max_ms < BUDGET_CONTEXT_NO_PROC_MS, (
            f"context/no_proc took {max_ms:.0f}ms (budget {BUDGET_CONTEXT_NO_PROC_MS}ms)"
        )

    def test_context_collect_with_processes(self, benchmark):
        from sentinel.core.context import ContextEngine

        engine = ContextEngine(collect_processes=True, process_limit=10)

        def run():
            return asyncio.run(engine.collect(include_processes=True))

        result = benchmark(run)
        assert result.cpu.get("percent") is not None
        max_ms = benchmark.stats.stats.max * 1000
        assert max_ms < BUDGET_CONTEXT_WITH_PROC_MS, (
            f"context/with_proc took {max_ms:.0f}ms (budget {BUDGET_CONTEXT_WITH_PROC_MS}ms)"
        )


class TestDbBenchmarks:
    """Benchmarks for database operations."""

    def test_config_get_set(self, benchmark):
        from repositories.database import DatabaseManager

        db = DatabaseManager()

        def ops():
            db.config_set_json("bench_test", {"value": time.time()})
            return db.config_get_json("bench_test")

        result = benchmark(ops)
        assert result is not None
        db.config_delete("bench_test")
        max_ms = benchmark.stats.stats.max * 1000
        assert max_ms < BUDGET_DB_MS, f"db/config took {max_ms:.0f}ms (budget {BUDGET_DB_MS}ms)"

    def test_audit_query(self, benchmark):
        resp = benchmark(client.get, "/v1/audit?limit=100")
        assert resp.status_code == 200
        max_ms = benchmark.stats.stats.max * 1000
        assert max_ms < BUDGET_DB_MS, f"db/audit took {max_ms:.0f}ms (budget {BUDGET_DB_MS}ms)"


class TestMemoryBenchmarks:
    """Benchmarks for operational memory operations."""

    def test_sqlite_memory_store_execution(self, benchmark):
        from sentinel.core.operational_memory import SQLiteBackend, ExecutionRecord
        from datetime import datetime, timezone

        mem = SQLiteBackend()
        record = ExecutionRecord(
            execution_id="bench-exec-1",
            timestamp=datetime.now(timezone.utc).isoformat(),
            utterance="benchmark test",
            intent={"action": "query", "target": "test"},
            plan={"steps": [], "description": "bench"},
            decision={"decision": "approve", "reason": "bench"},
            context_summary={},
            step_results=[],
            tool_result={"success": True},
            error=None,
            duration_ms=5.0,
        )
        benchmark(mem.store_execution, record)
        mem._db.execute("DELETE FROM execution_history WHERE execution_id = ?", ("bench-exec-1",))
        max_ms = benchmark.stats.stats.max * 1000
        assert max_ms < BUDGET_MEMORY_MS, f"memory/store took {max_ms:.0f}ms (budget {BUDGET_MEMORY_MS}ms)"

    def test_sqlite_memory_get_session_history(self, benchmark):
        from sentinel.core.operational_memory import SQLiteBackend

        mem = SQLiteBackend()
        benchmark(mem.get_session_history, "bench-session", 5)
        max_ms = benchmark.stats.stats.max * 1000
        assert max_ms < BUDGET_MEMORY_MS, f"memory/get_session took {max_ms:.0f}ms (budget {BUDGET_MEMORY_MS}ms)"
