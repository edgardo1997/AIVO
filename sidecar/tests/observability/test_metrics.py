"""Tests for Metrics System."""

from sentinel.observability.metrics.registry import MetricRegistry, Counter, Gauge, Histogram
from sentinel.observability.metrics.collector import MetricsCollector


class TestMetricRegistry:
    def test_counter_defaults(self):
        r = MetricRegistry()
        c = r.counter("test")
        assert c.value == 0.0
        c.inc()
        assert c.value == 1.0
        c.inc(5)
        assert c.value == 6.0

    def test_gauge(self):
        r = MetricRegistry()
        g = r.gauge("temp")
        g.set(42.5)
        assert g.value == 42.5

    def test_histogram(self):
        r = MetricRegistry()
        h = r.histogram("latency")
        h.observe(0.05)
        h.observe(0.2)
        h.observe(1.5)
        assert h.count == 3
        assert h.mean > 0
        assert h.percentiles["p50"] > 0

    def test_snapshot_structure(self):
        r = MetricRegistry()
        r.counter("req").inc(10)
        r.gauge("cpu").set(45)
        r.histogram("lat").observe(0.1)
        snap = r.snapshot()
        assert "counters" in snap
        assert "gauges" in snap
        assert "histograms" in snap
        assert snap["counters"]["req"]["value"] == 10.0

    def test_reset(self):
        r = MetricRegistry()
        r.counter("x").inc()
        r.reset()
        assert len(r.counters) == 0


class TestMetricsCollector:
    def test_record_request_updates_counters(self):
        r = MetricRegistry()
        mc = MetricsCollector(r)
        mc.record_request(model_id="gpt4", success=True, latency_ms=150)
        assert r.counter("requests_total").value == 1.0
        assert r.counter("model_usage", {"model": "gpt4"}).value == 1.0

    def test_record_failed_request(self):
        r = MetricRegistry()
        mc = MetricsCollector(r)
        mc.record_request(model_id="gpt4", success=False, latency_ms=500)
        assert r.counter("failed_requests").value == 1.0

    def test_record_component_duration(self):
        r = MetricRegistry()
        mc = MetricsCollector(r)
        mc.record_component_duration("planner", 250)
        h = r.histogram("component_duration", {"component": "planner"})
        assert h.count == 1

    def test_record_tool_execution(self):
        r = MetricRegistry()
        mc = MetricsCollector(r)
        mc.record_tool_execution("spotify", success=True, duration_ms=1200)
        c = r.counter("tool_executions", {"tool": "spotify", "status": "success"})
        assert c.value == 1.0

    def test_system_metrics_collection(self):
        r = MetricRegistry()
        mc = MetricsCollector(r)
        mc.collect_system_metrics()
        snap = r.snapshot()
        assert "gauges" in snap

    def test_summary_returns_snapshot(self):
        r = MetricRegistry()
        mc = MetricsCollector(r)
        mc.record_request("gpt4", True, 100)
        s = mc.summary()
        assert "counters" in s
        assert "uptime_seconds" in s
