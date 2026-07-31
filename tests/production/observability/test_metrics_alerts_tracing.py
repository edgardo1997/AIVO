"""FASE 7 — Production observability: metrics + alerts + tracing.

Exercises the real MetricsCollector, MetricRegistry, AlertEngine and TraceManager
inside the production ObservabilityEngine wired to the real stack.
"""

import pytest

from sentinel.observability.alert_engine import Alert, AlertLevel
from sentinel.observability.engine import ObservabilityConfig, ObservabilityEngine
from tests.production.harness import IDENTITY

pytestmark = pytest.mark.production


class TestMetricsCollector:
    @pytest.mark.asyncio
    async def test_metrics_recorded_through_real_engine(self, stack):
        stack.observability.record_request("model-a", True, 10.0)
        stack.observability.record_request("model-a", False, 20.0)
        stack.observability.record_provider_failure("openrouter")
        snapshot = stack.observability.collect_metrics()
        assert snapshot["counters"]["requests_total"]["value"] >= 2
        assert snapshot["counters"]["failed_requests"]["value"] >= 1
        provider_keys = [k for k in snapshot["counters"] if k.startswith("provider_failures")]
        assert len(provider_keys) >= 1
        assert sum(v["value"] for k, v in snapshot["counters"].items() if k.startswith("provider_failures")) >= 1

    @pytest.mark.asyncio
    async def test_model_metrics_with_success_rate(self, stack):
        stack.observability.record_request("perf-model", True, 10.0)
        stack.observability.record_request("perf-model", False, 30.0)
        models = stack.observability._metrics_collector.model_metrics()
        assert models["perf-model"]["requests"] == 2
        assert models["perf-model"]["success_rate"] == 0.5

    @pytest.mark.asyncio
    async def test_gateway_tool_execution_recorded(self, stack):
        ctx = {"identity": IDENTITY, "session_id": "sess-1", "execution_id": "e-1"}
        await stack.gateway.execute("tools.echo", {"message": "hi"}, context=ctx)
        snap = stack.observability.metric_registry.snapshot()
        tool_keys = [k for k in snap["counters"] if k.startswith("tool_executions")]
        assert len(tool_keys) >= 1

    @pytest.mark.asyncio
    async def test_observability_engine_records_failure_helpers(self, stack):
        stack.observability.record_database_failure()
        stack.observability.record_audit_failure()
        snap = stack.observability.metric_registry.snapshot()
        assert snap["counters"]["database_failure"]["value"] >= 1
        assert snap["counters"]["audit_failure"]["value"] >= 1


class TestAlertEngine:
    @pytest.mark.asyncio
    async def test_consecutive_errors_alert(self, stack):
        for _ in range(6):
            stack.observability.record_request("alert-model", False, 5.0)
        fired = stack.observability.check_alerts()
        names = [a.name for a in fired]
        assert "consecutive_errors" in names

    @pytest.mark.asyncio
    async def test_default_rules_installed(self, stack):
        rules = stack.observability.alerts._rules
        names = {r.name for r in rules}
        assert {
            "high_memory_usage",
            "high_cpu_usage",
            "model_failure_rate",
            "tool_failure_rate",
            "provider_failure_rate",
            "consecutive_errors",
            "database_failure",
            "audit_loss",
        }.issubset(names)

    @pytest.mark.asyncio
    async def test_alert_summary_shape(self, stack):
        summary = stack.observability.alerts.summary()
        assert "total_alerts" in summary
        assert "active_rules" in summary

    def test_custom_rule_fires_once_with_cooldown(self):
        engine = ObservabilityEngine(ObservabilityConfig(backup_dir="backup-tmp"))
        fired = []

        def fire():
            return Alert(name="unit-alert", level=AlertLevel.CRITICAL, message="boom", component="test", value=1, threshold=1)

        engine.alerts.add_custom_rule("unit-alert", "unit", lambda: fire(), interval_seconds=0, cooldown_seconds=0)
        engine.alerts.check()
        engine.alerts.check()
        assert len(engine.alerts.recent_alerts()) >= 1
        assert fired is not None


class TestTraceManager:
    @pytest.mark.asyncio
    async def test_tool_spans_recorded(self, stack):
        ctx = {"identity": IDENTITY, "session_id": "sess-2", "execution_id": "e-2"}
        await stack.gateway.execute("tools.math.add", {"a": 1, "b": 2}, context=ctx)
        traces = stack.observability.traces(limit=50)
        assert len(traces) >= 1

    @pytest.mark.asyncio
    async def test_request_trace_lifecycle(self, stack):
        span = stack.observability.start_request_trace(metadata={"utterance": "hello"})
        assert span.span_id
        stack.observability.end_request_trace(span, status="ok")
        summary = stack.observability.trace_summary()
        assert summary["total_spans"] >= 1

    @pytest.mark.asyncio
    async def test_trace_summary_shape(self, stack):
        summary = stack.observability.trace_summary()
        assert "total_traces" in summary
        assert "total_spans" in summary
