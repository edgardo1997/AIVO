import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock
import pytest

from sentinel.core.alerting import AlertManager, AlertSeverity, Alert, ALERT_SOURCES


class TestAlertSeverity:
    def test_values(self):
        assert AlertSeverity.INFO.value == "info"
        assert AlertSeverity.WARNING.value == "warning"
        assert AlertSeverity.CRITICAL.value == "critical"


class TestAlert:
    def test_to_dict(self):
        a = Alert(
            id="a1",
            alert_type="test",
            severity=AlertSeverity.WARNING,
            title="Test Alert",
            message="Something happened",
            source="test",
        )
        d = a.to_dict()
        assert d["id"] == "a1"
        assert d["severity"] == "warning"
        assert d["title"] == "Test Alert"
        assert d["acknowledged"] is False

    def test_acknowledged(self):
        a = Alert(id="a1", alert_type="test", severity=AlertSeverity.INFO, title="t", message="m")
        a.acknowledged = True
        assert a.to_dict()["acknowledged"] is True


class TestAlertManager:
    def test_emit_creates_alert(self):
        am = AlertManager()
        a = am.emit("test", AlertSeverity.INFO, "Title", "Message")
        assert a.id is not None
        assert a.title == "Title"
        assert a.message == "Message"

    def test_emit_stores_alert(self):
        am = AlertManager()
        am.emit("t1", AlertSeverity.INFO, "T1", "M1")
        alerts = am.list()
        assert len(alerts) == 1
        assert alerts[0]["title"] == "T1"

    def test_list_empty(self):
        am = AlertManager()
        assert am.list() == []

    def test_list_limit(self):
        am = AlertManager()
        for i in range(10):
            am.emit(f"t{i}", AlertSeverity.INFO, f"T{i}", f"M{i}")
        alerts = am.list(limit=3)
        assert len(alerts) == 3

    def test_list_filter_source(self):
        am = AlertManager()
        am.emit("t1", AlertSeverity.INFO, "T1", "M1", source="cost")
        am.emit("t2", AlertSeverity.INFO, "T2", "M2", source="performance")
        assert len(am.list(source="cost")) == 1
        assert len(am.list(source="performance")) == 1

    def test_list_filter_severity(self):
        am = AlertManager()
        am.emit("t1", AlertSeverity.INFO, "T1", "M1")
        am.emit("t2", AlertSeverity.CRITICAL, "T2", "M2")
        assert len(am.list(severity=AlertSeverity.INFO)) == 1
        assert len(am.list(severity=AlertSeverity.CRITICAL)) == 1

    def test_list_filter_acknowledged(self):
        am = AlertManager()
        am.emit("t1", AlertSeverity.INFO, "T1", "M1")
        a2 = am.emit("t2", AlertSeverity.INFO, "T2", "M2")
        am.acknowledge(a2.id)
        assert len(am.list(acknowledged=False)) == 1
        assert len(am.list(acknowledged=True)) == 1

    def test_acknowledge(self):
        am = AlertManager()
        a = am.emit("t", AlertSeverity.INFO, "T", "M")
        assert am.acknowledge(a.id) is True
        assert am.acknowledge("nonexistent") is False

    def test_acknowledge_all(self):
        am = AlertManager()
        am.emit("t1", AlertSeverity.INFO, "T1", "M1")
        am.emit("t2", AlertSeverity.INFO, "T2", "M2")
        assert am.acknowledge_all() == 2

    def test_acknowledge_all_by_source(self):
        am = AlertManager()
        am.emit("t1", AlertSeverity.INFO, "T1", "M1", source="cost")
        am.emit("t2", AlertSeverity.INFO, "T2", "M2", source="performance")
        assert am.acknowledge_all(source="cost") == 1
        assert am.acknowledge_all(source="cost") == 0

    def test_clear_acknowledged_only(self):
        am = AlertManager()
        a1 = am.emit("t1", AlertSeverity.INFO, "T1", "M1")
        am.emit("t2", AlertSeverity.INFO, "T2", "M2")
        am.acknowledge(a1.id)
        assert am.clear(acknowledged_only=True) == 1
        assert len(am.list()) == 1

    def test_clear_all(self):
        am = AlertManager()
        am.emit("t1", AlertSeverity.INFO, "T1", "M1")
        am.emit("t2", AlertSeverity.INFO, "T2", "M2")
        assert am.clear(acknowledged_only=False) == 2
        assert len(am.list()) == 0

    def test_handler_called(self):
        am = AlertManager()
        calls = []
        am.register_handler(lambda a: calls.append(a.id))
        a = am.emit("t", AlertSeverity.INFO, "T", "M")
        assert len(calls) == 1
        assert calls[0] == a.id

    def test_handler_exception_does_not_break(self):
        am = AlertManager()

        def bad_handler(a):
            raise RuntimeError("handler failed")

        am.register_handler(bad_handler)
        a = am.emit("t", AlertSeverity.INFO, "T", "M")
        assert a is not None

    def test_max_alerts_respected(self):
        am = AlertManager(max_alerts=5)
        for i in range(10):
            am.emit(f"t{i}", AlertSeverity.INFO, f"T{i}", f"M{i}")
        assert len(am.list()) == 5

    def test_stats(self):
        am = AlertManager()
        am.emit("t1", AlertSeverity.INFO, "T1", "M1", source="cost")
        am.emit("t2", AlertSeverity.WARNING, "T2", "M2", source="performance")
        stats = am.stats()
        assert stats["total"] == 2
        assert stats["unacknowledged"] == 2
        assert stats["by_source"]["cost"] == 1
        assert stats["by_source"]["performance"] == 1

    def test_check_all_no_trackers(self):
        am = AlertManager()
        assert am.check_all() == 0

    def test_emit_with_data(self):
        am = AlertManager()
        a = am.emit("test", AlertSeverity.CRITICAL, "Critical", "Something broke", source="system", data={"code": 500})
        assert a.data["code"] == 500
        d = a.to_dict()
        assert d["data"]["code"] == 500

    def test_alert_sources_list(self):
        assert "cost" in ALERT_SOURCES
        assert "performance" in ALERT_SOURCES
        assert "circuit_breaker" in ALERT_SOURCES

    def test_to_dict(self):
        am = AlertManager()
        am.emit("t", AlertSeverity.INFO, "T", "M")
        d = am.to_dict()
        assert "alerts" in d
        assert "stats" in d
        assert len(d["alerts"]) == 1


class TestAlertingAPI:
    def setup_method(self):
        from modules.sentinel_bridge import reset_bridge

        reset_bridge()

    def test_list_alerts(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        resp = client.get("/api/sentinel/alerts")
        assert resp.status_code == 200
        data = resp.json()
        assert "alerts" in data
        assert "stats" in data

    def test_acknowledge_alert(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        resp = client.post("/api/sentinel/alerts/acknowledge", json={})
        assert resp.status_code == 200
        assert "acknowledged" in resp.json()

    def test_check_alerts(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        resp = client.post("/api/sentinel/alerts/check")
        assert resp.status_code == 200
        data = resp.json()
        assert "checked" in data
        assert "new_alerts" in data
        assert "stats" in data

    def test_clear_alerts(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        resp = client.post("/api/sentinel/alerts/clear")
        assert resp.status_code == 200
        assert "cleared" in resp.json()
