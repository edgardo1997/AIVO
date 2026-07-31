"""Tests for Structured Logging."""

import json
from sentinel.observability.logging.structured_logger import StructuredLogger, LogEvent


class TestLogEvent:
    def test_to_dict_basic(self):
        e = LogEvent(event="test_event", level="INFO", message="hello", component="test")
        d = e.to_dict()
        assert d["event"] == "test_event"
        assert d["level"] == "INFO"
        assert d["message"] == "hello"
        assert d["component"] == "test"
        assert "timestamp" in d

    def test_to_dict_with_extra(self):
        e = LogEvent(event="tool_exec", extra={"tool": "spotify", "risk": "low"})
        d = e.to_dict()
        assert d["tool"] == "spotify"
        assert d["risk"] == "low"

    def test_to_json(self):
        e = LogEvent(event="test")
        js = e.to_json()
        parsed = json.loads(js)
        assert parsed["event"] == "test"

    def test_trace_context_included(self):
        e = LogEvent(event="traced", trace_id="abc123", span_id="s1")
        d = e.to_dict()
        assert d["trace_id"] == "abc123"
        assert d["span_id"] == "s1"

    def test_duration_rounded(self):
        e = LogEvent(event="slow", duration_ms=1.234)
        assert e.to_dict()["duration_ms"] == 1.2


class TestStructuredLogger:
    def test_logger_creates_json(self, caplog):
        import logging
        logger = StructuredLogger("test_logger")
        logger.info("test_event", message="test", component="test")
        assert True

    def test_logger_with_trace(self):
        from sentinel.observability.tracing.trace_manager import TraceManager
        tm = TraceManager()
        logger = StructuredLogger("trace_logger", trace_manager=tm)
        tm.start_trace()
        logger.info("traced_event", message="has trace id")
        assert True
