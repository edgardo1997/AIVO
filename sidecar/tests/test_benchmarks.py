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
from services.rate_limiter import SlidingWindowRateLimiter

client = TestClient(app)
perm_svc.set_level("admin")

# Create an unlimited rate limiter for benchmarks
_unlimited = SlidingWindowRateLimiter(window_seconds=1, max_buckets=1)
_original_allow = _rate_limiter.allow
_rate_limiter.allow = lambda key, limit=999999: type('_', (), {'allowed': True, 'remaining': 999, 'retry_after': 0})()


@pytest.fixture(scope="session", autouse=True)
def warmup():
    """Warm up the orchestrator singleton (first-call latency is high)."""
    _rate_limiter.clear()
    client.post("/api/sentinel/process", json={"utterance": "cpu usage"})
    client.post("/v1/execute", json={"tool_id": "system.cpu", "params": {}})


class TestPipelineBenchmarks:
    """Benchmarks for the core orchestrator pipeline."""

    def test_process_cpu(self, benchmark):
        resp = benchmark(client.post, "/api/sentinel/process", json={"utterance": "cpu usage"})
        assert resp.status_code == 200

    def test_process_system_health_multi_step(self, benchmark):
        resp = benchmark(client.post, "/api/sentinel/process", json={"utterance": "analyze system health"})
        assert resp.status_code == 200

    def test_dry_run_skip_simulation(self, benchmark):
        resp = benchmark(client.post, "/api/sentinel/process", json={
            "utterance": "cpu usage", "dry_run": True,
        })
        assert resp.status_code == 200

    def test_v1_execute_cpu(self, benchmark):
        resp = benchmark(client.post, "/v1/execute", json={"tool_id": "system.cpu", "params": {}})
        assert resp.status_code == 200

    def test_v1_execute_system_info(self, benchmark):
        resp = benchmark(client.post, "/v1/execute", json={"tool_id": "system.info", "params": {}})
        assert resp.status_code == 200

    def test_v1_execute_app_discovery(self, benchmark):
        resp = benchmark(client.post, "/v1/execute", json={
            "tool_id": "app.discovery", "params": {"action": "list"},
        })
        assert resp.status_code == 200


class TestApiEndpointBenchmarks:
    """Benchmarks for read-only API endpoints."""

    def test_health(self, benchmark):
        resp = benchmark(client.get, "/api/health")
        assert resp.status_code == 200

    def test_capabilities(self, benchmark):
        resp = benchmark(client.get, "/api/sentinel/capabilities")
        assert resp.status_code == 200

    def test_goals(self, benchmark):
        resp = benchmark(client.get, "/api/sentinel/goals")
        assert resp.status_code == 200

    def test_audit(self, benchmark):
        resp = benchmark(client.get, "/v1/audit?limit=10")
        assert resp.status_code == 200

    def test_agents_list(self, benchmark):
        resp = benchmark(client.get, "/v1/agents")
        assert resp.status_code == 200

    def test_triggers_list(self, benchmark):
        resp = benchmark(client.get, "/v1/triggers")
        assert resp.status_code == 200

    def test_hardening_config(self, benchmark):
        resp = benchmark(client.get, "/api/sentinel/hardening/config")
        assert resp.status_code == 200

    def test_hardening_health(self, benchmark):
        resp = benchmark(client.get, "/api/sentinel/hardening/health")
        assert resp.status_code == 200

    def test_info(self, benchmark):
        resp = benchmark(client.get, "/api/info")
        assert resp.status_code == 200

    def test_profile(self, benchmark):
        resp = benchmark(client.get, "/v1/profile")
        assert resp.status_code == 200

    def test_vault_status(self, benchmark):
        resp = benchmark(client.get, "/api/sentinel/vault/status")
        assert resp.status_code == 200


class TestContextEngineBenchmarks:
    """Benchmarks for the context engine (psutil calls)."""

    def test_context_collect_no_processes(self, benchmark):
        from sentinel.core.context import ContextEngine
        engine = ContextEngine(collect_processes=False)

        def run():
            return asyncio.run(engine.collect(include_processes=False))

        result = benchmark(run)
        assert result.cpu.get("percent") is not None

    def test_context_collect_with_processes(self, benchmark):
        from sentinel.core.context import ContextEngine
        engine = ContextEngine(collect_processes=True, process_limit=10)

        def run():
            return asyncio.run(engine.collect(include_processes=True))

        result = benchmark(run)
        assert result.cpu.get("percent") is not None


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

    def test_audit_query(self, benchmark):
        resp = benchmark(client.get, "/v1/audit?limit=100")
        assert resp.status_code == 200


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

    def test_sqlite_memory_get_session_history(self, benchmark):
        from sentinel.core.operational_memory import SQLiteBackend
        mem = SQLiteBackend()
        benchmark(mem.get_session_history, "bench-session", 5)
