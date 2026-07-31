"""Tests for Recovery Manager, Alert Engine, and graceful failure."""

from sentinel.observability.recovery.recovery_manager import RecoveryManager, SystemState
from sentinel.observability.alert_engine import AlertEngine, Alert, AlertRule, AlertLevel


class TestRecoveryManager:
    def test_initial_state_healthy(self):
        rm = RecoveryManager()
        assert rm.state == SystemState.HEALTHY

    def test_state_transition(self):
        rm = RecoveryManager()
        rm.state = SystemState.DEGRADED
        assert rm.state == SystemState.DEGRADED
        rm.state = SystemState.HEALTHY
        assert rm.state == SystemState.HEALTHY

    def test_create_recovery_point(self):
        rm = RecoveryManager()
        rp = rm.create_recovery_point(description="before config change")
        assert rp.id
        assert rp.description == "before config change"

    def test_record_failure(self):
        rm = RecoveryManager()
        rm.record_failure("openai")
        assert rm._failure_counts["openai"] == 1
        rm.record_failure("openai")
        assert rm._failure_counts["openai"] == 2

    def test_attempt_recovery_no_action(self):
        rm = RecoveryManager()
        result = rm.attempt_recovery("unknown")
        assert not result
        assert rm.state == SystemState.DEGRADED

    def test_attempt_recovery_success(self):
        rm = RecoveryManager()
        rm.register_recovery_action("test", lambda: True)
        result = rm.attempt_recovery("test")
        assert result
        assert rm.state == SystemState.HEALTHY

    def test_attempt_recovery_failure(self):
        rm = RecoveryManager()
        rm.register_recovery_action("test", lambda: False)
        result = rm.attempt_recovery("test")
        assert not result
        assert rm.state == SystemState.DEGRADED

    def test_summary(self):
        rm = RecoveryManager()
        s = rm.summary()
        assert s["state"] == "healthy"
        assert "uptime_seconds" in s


class TestAlertEngine:
    def test_no_alerts_initially(self):
        ae = AlertEngine()
        assert len(ae.recent_alerts()) == 0

    def test_add_rule_and_check(self):
        ae = AlertEngine()
        ae.add_custom_rule("high_mem", "Memory > 90%", lambda: Alert(name="high_mem", level=AlertLevel.WARNING, message="Memory high", component="memory"))
        fired = ae.check()
        assert len(fired) == 1
        assert fired[0].name == "high_mem"

    def test_rule_cooldown(self):
        ae = AlertEngine()
        count = 0

        def check():
            nonlocal count
            count += 1
            return Alert(name="frequent", level=AlertLevel.WARNING, message="alert", component="test")

        ae.add_custom_rule("frequent", "test", check, interval_seconds=0, cooldown_seconds=999)
        ae.check()
        ae.check()
        assert count == 2
        assert len(ae.recent_alerts()) == 1

    def test_rule_does_not_fire_if_check_returns_none(self):
        ae = AlertEngine()
        ae.add_custom_rule("ok", "all good", lambda: None)
        fired = ae.check()
        assert len(fired) == 0

    def test_recent_alerts_by_level(self):
        ae = AlertEngine()
        ae.add_custom_rule("warn", "w", lambda: Alert(name="warn", level=AlertLevel.WARNING, message="warn", component="x"), interval_seconds=0, cooldown_seconds=0)
        ae.add_custom_rule("crit", "c", lambda: Alert(name="crit", level=AlertLevel.CRITICAL, message="crit", component="x"), interval_seconds=0, cooldown_seconds=0)
        ae.check_all()
        ae.check_all()
        warnings = ae.recent_alerts(level=AlertLevel.WARNING)
        assert len(warnings) >= 1
        assert all(a.level == AlertLevel.WARNING for a in warnings)

    def test_summary_structure(self):
        ae = AlertEngine()
        ae.add_custom_rule("test", "test", lambda: Alert(name="test", level=AlertLevel.INFO, message="test", component="x"))
        ae.check()
        s = ae.summary()
        assert s["total_alerts"] >= 1
        assert "by_level" in s

    def test_clear(self):
        ae = AlertEngine()
        ae.add_custom_rule("test", "t", lambda: Alert(name="test", level=AlertLevel.INFO, message="t", component="x"))
        ae.check()
        assert len(ae.recent_alerts()) > 0
        ae.clear()
        assert len(ae.recent_alerts()) == 0
