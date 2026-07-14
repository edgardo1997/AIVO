import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sentinel.core.observability import ObservabilityService


def test_trace_lifecycle_and_correlation():
    service = ObservabilityService()
    span = service.start("filesystem.read", execution_id="exec-123", parent_id="root-span")
    time.sleep(0.002)
    trace = service.finish(span, True, quality={"passed": True, "redacted": False, "issues": []})
    assert trace["trace_id"] == "exec-123"
    assert trace["parent_id"] == "root-span"
    assert trace["duration_ms"] >= 0
    assert "params" not in trace


def test_summary_combines_latency_quality_and_errors():
    service = ObservabilityService()
    ok = service.start("system.info")
    service.finish(ok, True, quality={"passed": True, "redacted": True, "issues": ["redacted"]})
    failed = service.start("web.navigate")
    service.finish(failed, False, "transient", {"passed": False, "redacted": False, "issues": ["large"]})
    summary = service.summary()
    assert summary["total_executions"] == 2
    assert summary["success_rate"] == 50.0
    assert summary["quality"] == {"blocked": 1, "redacted": 1}
    assert summary["errors_by_category"] == {"transient": 1}
    assert set(summary["latency_ms"]) == {"average", "p50", "p95", "maximum"}


def test_trace_buffer_is_bounded_and_filterable():
    service = ObservabilityService(max_traces=2)
    for tool_id in ("one", "two", "two"):
        span = service.start(tool_id)
        service.finish(span, True)
    assert len(service.traces()) == 2
    assert len(service.traces(tool_id="two")) == 2
    assert service.summary()["total_executions"] == 2


def test_unknown_span_is_ignored():
    service = ObservabilityService()
    assert service.finish("missing", False) is None
    assert service.summary()["active_spans"] == 0


def test_observability_endpoints_serialize_integral_view():
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    overview = client.get("/api/sentinel/observability/overview")
    traces = client.get("/api/sentinel/observability/traces")
    assert overview.status_code == 200
    assert traces.status_code == 200
    assert {"costs", "traces", "latency_baselines", "alerts"} <= set(overview.json())
