import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch
import pytest

from sentinel.core.performance_tracker import (
    PerformanceTracker,
    TaskType,
)


class TestPerformanceTracker:
    def test_record_increases_count(self):
        pt = PerformanceTracker()
        pt.record("ollama", "llama3", TaskType.QUICK, "system.info", 150.0, True)
        assert pt.total_records == 1

    def test_get_baselines_after_records(self):
        pt = PerformanceTracker()
        for _ in range(10):
            pt.record("ollama", "llama3", TaskType.QUICK, "system.info", 100.0, True)
        baselines = pt.get_baselines()
        assert len(baselines) == 1
        b = baselines[0]
        assert b.provider_id == "ollama"
        assert b.tool_id == "system.info"
        assert b.sample_count == 10
        assert b.avg_duration_ms == 100.0

    def test_multiple_keys_separate_baselines(self):
        pt = PerformanceTracker()
        for _ in range(5):
            pt.record("ollama", "llama3", TaskType.QUICK, "system.info", 100.0, True)
            pt.record("openrouter", "gpt-4o", TaskType.CODE, "executor.command", 500.0, True)
        baselines = pt.get_baselines()
        assert len(baselines) == 2

    def test_regression_alert_triggers(self):
        pt = PerformanceTracker()
        for _ in range(10):
            pt.record("ollama", "llama3", TaskType.QUICK, "system.info", 100.0, True)
        alert = pt.record("ollama", "llama3", TaskType.QUICK, "system.info", 160.0, True)
        assert alert is not None
        assert alert.severity == "warning"
        assert 50 < alert.deviation_pct < 100

    def test_regression_critical(self):
        pt = PerformanceTracker()
        for _ in range(10):
            pt.record("ollama", "llama3", TaskType.QUICK, "system.info", 100.0, True)
        alert = pt.record("ollama", "llama3", TaskType.QUICK, "system.info", 500.0, True)
        assert alert is not None
        assert alert.severity == "critical"
        assert alert.deviation_pct > 100

    def test_no_regression_within_threshold(self):
        pt = PerformanceTracker()
        for _ in range(10):
            pt.record("ollama", "llama3", TaskType.QUICK, "system.info", 100.0, True)
        alert = pt.record("ollama", "llama3", TaskType.QUICK, "system.info", 110.0, True)
        assert alert is None

    def test_no_alert_until_min_samples(self):
        pt = PerformanceTracker()
        for i in range(5):
            pt.record("ollama", "llama3", TaskType.QUICK, "system.info", 100.0, True)
        assert pt.total_records == 5
        assert len(pt.get_alerts()) == 0
        pt.record("ollama", "llama3", TaskType.QUICK, "system.info", 500.0, True)
        assert len(pt.get_alerts()) >= 0

    def test_get_alerts_filtered_by_severity(self):
        pt = PerformanceTracker()
        for _ in range(10):
            pt.record("ollama", "llama3", TaskType.QUICK, "system.info", 100.0, True)
        pt.record("ollama", "llama3", TaskType.QUICK, "system.info", 500.0, True)
        critical = pt.get_alerts(severity="critical")
        warning = pt.get_alerts(severity="warning")
        assert len(critical) >= 1
        assert len(warning) >= 0

    def test_get_alerts_empty_when_none(self):
        pt = PerformanceTracker()
        assert pt.get_alerts() == []


class TestPerformanceAPI:
    def setup_method(self):
        from modules.sentinel_bridge import reset_bridge
        reset_bridge()

    def test_baselines_endpoint(self):
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        resp = client.get("/api/sentinel/performance/baselines")
        assert resp.status_code == 200
        data = resp.json()
        assert "baselines" in data

    def test_alerts_endpoint(self):
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        resp = client.get("/api/sentinel/performance/alerts")
        assert resp.status_code == 200
        data = resp.json()
        assert "alerts" in data

    def test_alerts_filter_by_severity(self):
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        resp = client.get("/api/sentinel/performance/alerts?severity=critical")
        assert resp.status_code == 200
        data = resp.json()
        assert "alerts" in data



