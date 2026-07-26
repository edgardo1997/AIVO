"""Tests for enhanced observability: health checks, distributed traces, observability center."""

import pytest

from sentinel.core.observability import ObservabilityService
from sentinel.core.observability_center import ObservabilityCenter
from sentinel.core.structured_log import StructuredFormatter, configure_json_logging


class TestObservabilityHealth:
    @pytest.mark.unit
    def test_health_returns_healthy_initially(self):
        obs = ObservabilityService(max_traces=100)
        health = obs.health()
        assert "status" in health
        assert "active_spans" in health

    @pytest.mark.unit
    def test_health_tracks_active_spans(self):
        obs = ObservabilityService(max_traces=100)
        sid = obs.start("test.tool", "exec_1")
        health = obs.health()
        assert health["active_spans"] == 1
        obs.finish(sid, True)
        health = obs.health()
        assert health["active_spans"] == 0

    @pytest.mark.unit
    def test_health_recent_failures(self):
        obs = ObservabilityService(max_traces=100)
        for i in range(10):
            success = i % 2 == 0
            sid = obs.start(f"tool.{i}", f"exec_{i}")
            obs.finish(sid, success)
        health = obs.health()
        assert health["recent_executions"] > 0
        assert "recent_failure_rate_pct" in health

    @pytest.mark.unit
    def test_health_full_structure(self):
        obs = ObservabilityService(max_traces=100)
        health = obs.health()
        for key in (
            "status",
            "active_spans",
            "recent_executions",
            "recent_failure_rate_pct",
            "total_executions",
            "timestamp",
        ):
            assert key in health


class TestObservabilityTrace:
    @pytest.mark.unit
    def test_span_tree_returns_spans(self):
        obs = ObservabilityService(max_traces=100)
        sid1 = obs.start("parent.tool", "trace_abc")
        sid2 = obs.start("child.tool", "trace_abc", parent_id=sid1)
        obs.finish(sid2, True)
        obs.finish(sid1, True)
        tree = obs.span_tree("trace_abc")
        assert len(tree) >= 1
        root = tree[0]
        assert root["span_id"] == sid1

    @pytest.mark.unit
    def test_trace_returns_full_trace(self):
        obs = ObservabilityService(max_traces=100)
        sid = obs.start("my.tool", "trace_xyz")
        obs.finish(sid, True)
        trace = obs.trace("trace_xyz")
        assert trace is not None
        assert trace["trace_id"] == "trace_xyz"
        assert trace["total_spans"] > 0
        assert "total_duration_ms" in trace

    @pytest.mark.unit
    def test_trace_missing_returns_none(self):
        obs = ObservabilityService(max_traces=100)
        assert obs.trace("nonexistent") is None

    @pytest.mark.unit
    def test_parent_child_relationship(self):
        obs = ObservabilityService(max_traces=100)
        parent = obs.start("parent", "trace_parent")
        child = obs.start("child", "trace_parent", parent_id=parent)
        obs.finish(child, True)
        obs.finish(parent, True)
        tree = obs.span_tree("trace_parent")
        assert len(tree) == 1
        assert tree[0]["span_id"] == parent
        assert len(tree[0].get("children", [])) == 1
        assert tree[0]["children"][0]["span_id"] == child


class TestObservabilityCenter:
    @pytest.mark.unit
    def test_dashboard_defaults(self):
        center = ObservabilityCenter()
        dash = center.dashboard()
        assert dash["status"] == "unavailable"
        assert "health" in dash
        assert "execution" in dash

    @pytest.mark.unit
    def test_dashboard_with_observability(self):
        obs = ObservabilityService(max_traces=100)
        center = ObservabilityCenter(observability=obs)
        dash = center.dashboard()
        assert dash["status"] in ("healthy", "degraded")

    @pytest.mark.unit
    def test_component_status(self):
        center = ObservabilityCenter()
        status = center.component_status()
        assert "observability" in status
        assert "pipeline_metrics" in status
        assert "rate_limiter" in status
        assert "policy_engine" in status

    @pytest.mark.unit
    def test_setters(self):
        obs = ObservabilityService(max_traces=100)
        center = ObservabilityCenter()
        center.set_observability(obs)
        center.set_pipeline_metrics(None)
        center.set_rate_limiter(None)
        center.set_policy_engine(None)
        dash = center.dashboard()
        assert dash is not None


class TestStructuredLog:
    @pytest.mark.unit
    def test_formatter_creates_json(self):
        import logging

        fmt = StructuredFormatter()
        record = logging.LogRecord("test.logger", logging.INFO, "test.py", 1, "hello world", (), None)
        output = fmt.format(record)
        import json

        parsed = json.loads(output)
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test.logger"
        assert parsed["message"] == "hello world"

    @pytest.mark.unit
    def test_formatter_includes_timestamp(self):
        import logging

        fmt = StructuredFormatter()
        record = logging.LogRecord("t", logging.INFO, "f", 1, "msg", (), None)
        output = fmt.format(record)
        import json

        parsed = json.loads(output)
        assert "timestamp" in parsed

    @pytest.mark.unit
    def test_configure_json_logging(self):
        import logging

        logger = logging.getLogger("test_json_" + str(id(self)))
        configure_json_logging(logger)
        assert len(logger.handlers) >= 1
        assert isinstance(logger.handlers[0].formatter, StructuredFormatter)
