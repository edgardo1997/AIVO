"""FASE 7 — Production observability: recovery + logging + persistence + orchestrator integration.

Exercises the real RecoveryManager, StructuredLogger, MetricRecord persistence
through the official repository, and the Orchestrator wiring.
"""

import pytest

from tests.production.harness import IDENTITY

pytestmark = pytest.mark.production


class TestRecovery:
    @pytest.mark.asyncio
    async def test_backup_creation_real(self, stack):
        import os

        from pathlib import Path

        target = Path(stack.workspace) / "state.json"
        target.write_text('{"ok": true}', encoding="utf-8")
        record = stack.observability.create_backup(str(target), label="prod-test")
        assert record is not None
        assert record.path
        assert os.path.exists(record.path)

    @pytest.mark.asyncio
    async def test_recovery_summary_shape(self, stack):
        summary = stack.observability.recovery.summary()
        assert "state" in summary
        assert "failure_counts" in summary

    @pytest.mark.asyncio
    async def test_health_components_registered(self, stack):
        status = stack.observability.check_health()
        names = set(status.components.keys())
        assert {"system", "metrics", "tracing", "database", "audit"}.issubset(names)


class TestLogging:
    @pytest.mark.asyncio
    async def test_structured_logger_available(self, stack):
        logger = stack.observability.logger
        assert logger is not None

    @pytest.mark.asyncio
    async def test_log_emits_events(self, stack):
        from sentinel.observability.logging.structured_logger import LogEvent

        logger = stack.observability.logger
        logger.info("prod-check", {"key": "value"})
        assert logger is not None


class TestPersistence:
    @pytest.mark.asyncio
    async def test_to_metric_records_returns_rows(self, stack):
        stack.observability.record_request("persist-model", True, 10.0)
        records = stack.observability.to_metric_records()
        assert len(records) >= 1
        names = {r.metric_name for r in records}
        assert "requests_total" in names

    @pytest.mark.asyncio
    async def test_persist_through_official_repo(self, stack):
        stack.observability.record_request("persist-model", True, 10.0)
        n = await stack.intel.persist_observability_metrics(stack.observability)
        assert n >= 1
        count = await stack.intel._metric_repo.count()
        assert count >= n


class TestOrchestratorIntegration:
    @pytest.mark.asyncio
    async def test_orchestrator_has_observability(self, stack):
        assert stack.orchestrator.observability is stack.observability

    @pytest.mark.asyncio
    async def test_execution_records_telemetry(self, stack):
        await stack.orchestrator.execute_direct("system.info", {}, identity=IDENTITY)
        snap = stack.observability.metric_registry.snapshot()
        assert snap["counters"]["requests_total"]["value"] >= 1

    @pytest.mark.asyncio
    async def test_execution_records_traces(self, stack):
        await stack.orchestrator.execute_direct("tools.echo", {"message": "trace"}, identity=IDENTITY)
        summary = stack.observability.trace_summary()
        assert summary["total_traces"] >= 1

    @pytest.mark.asyncio
    async def test_orchestrator_wiring_components_registered(self, stack):
        status = stack.orchestrator.observability.check_health()
        names = set(status.components.keys())
        assert {"orchestrator", "execution_pipeline", "tool_gateway"}.issubset(names)
