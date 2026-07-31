"""Tests for Distributed Tracing and TraceID propagation."""

import time
from sentinel.observability.tracing.trace_manager import TraceManager, SpanContext


class TestTraceManager:
    def test_generate_ids(self):
        tm = TraceManager()
        tid = tm.generate_trace_id()
        sid = tm.generate_span_id()
        assert len(tid) == 12
        assert len(sid) == 8

    def test_start_trace_creates_span(self):
        tm = TraceManager()
        span = tm.start_trace(component="runtime")
        assert span.trace_id
        assert span.span_id
        assert span.component == "runtime"
        assert tm.current_trace_id == span.trace_id

    def test_start_span_under_trace(self):
        tm = TraceManager()
        root = tm.start_trace(component="root")
        child = tm.start_span(component="child")
        assert child.trace_id == root.trace_id
        assert child.parent_span_id == root.span_id

    def test_end_span_records_duration(self):
        tm = TraceManager()
        span = tm.start_trace(component="test")
        # Windows timer granularity (~15.6 ms) can collapse shorter sleeps to 0 ms.
        time.sleep(0.05)
        tm.end_span(span, status="ok")
        assert span.duration_ms > 0
        assert span.status == "ok"

    def test_get_trace_returns_spans(self):
        tm = TraceManager()
        tm.start_trace(component="req")
        tm.start_span(component="step1")
        spans = tm.get_trace(tm.current_trace_id)
        assert len(spans) == 2

    def test_trace_tree(self):
        tm = TraceManager()
        tm.start_trace(component="root")
        tm.start_span(component="child")
        tree = tm.get_trace_tree(tm.current_trace_id)
        assert tree["trace_id"]
        assert len(tree["spans"]) == 2

    def test_trace_summary(self):
        tm = TraceManager()
        tm.start_trace()
        s = tm.trace_summary()
        assert s["total_traces"] >= 1

    def test_create_context_from_request(self):
        tm = TraceManager()
        span = tm.create_context_from_request(request_id="abc123")
        assert span.trace_id == "abc123"

    def test_span_to_dict(self):
        sc = SpanContext(trace_id="t1", span_id="s1", component="test")
        d = sc.to_dict()
        assert d["trace_id"] == "t1"
        assert d["component"] == "test"
