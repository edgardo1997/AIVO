"""Tests for Health System."""

from sentinel.observability.health.health_checker import HealthChecker, HealthState, HealthStatus, ComponentHealth
from sentinel.observability.health.dependency_check import DependencyChecker


class TestHealthChecker:
    def test_healthy_by_default(self):
        hc = HealthChecker()
        status = hc.check_all()
        assert status.state == HealthState.HEALTHY

    def test_register_and_check_component(self):
        hc = HealthChecker()
        hc.register("test", lambda: ComponentHealth(name="test", state=HealthState.HEALTHY))
        status = hc.check_all()
        assert "test" in status.components
        assert status.components["test"].state == HealthState.HEALTHY

    def test_failed_component_degrades_status(self):
        hc = HealthChecker()
        hc.register("good", lambda: ComponentHealth(name="good", state=HealthState.HEALTHY))
        hc.register("bad", lambda: ComponentHealth(name="bad", state=HealthState.FAILED, error="down"))
        status = hc.check_all()
        assert status.state == HealthState.FAILED
        assert status.components["bad"].error == "down"

    def test_degraded_component(self):
        hc = HealthChecker()
        hc.register("slow", lambda: ComponentHealth(name="slow", state=HealthState.DEGRADED, latency_ms=5000))
        status = hc.check_all()
        assert status.state == HealthState.DEGRADED

    def test_check_exception_returns_failed(self):
        hc = HealthChecker()

        def broken():
            raise RuntimeError("kaboom")

        hc.register("broken", broken)
        ch = hc.check("broken")
        assert ch.state == HealthState.FAILED
        assert "kaboom" in (ch.error or "")

    def test_check_subset(self):
        hc = HealthChecker()
        hc.register("a", lambda: ComponentHealth(name="a", state=HealthState.HEALTHY))
        hc.register("b", lambda: ComponentHealth(name="b", state=HealthState.FAILED))
        status = hc.check_subset(["a"])
        assert status.state == HealthState.HEALTHY
        assert "b" not in status.components

    def test_uptime_increases(self):
        import time
        hc = HealthChecker()
        u1 = hc.uptime
        time.sleep(0.05)
        u2 = hc.uptime
        assert u2 > u1

    def test_health_status_to_dict(self):
        hs = HealthStatus(state=HealthState.HEALTHY, uptime_seconds=3600, version="2.0")
        d = hs.to_dict()
        assert d["status"] == "healthy"
        assert d["uptime"] == "1h0m0s"

    def test_worse_ordering(self):
        assert HealthChecker._worse(HealthState.HEALTHY, HealthState.HEALTHY) is False
        assert HealthChecker._worse(HealthState.FAILED, HealthState.HEALTHY) is True
        assert HealthChecker._worse(HealthState.DEGRADED, HealthState.RECOVERING) is True


class TestDependencyChecker:
    def test_default_all_healthy(self):
        dc = DependencyChecker()
        result = dc.check_all()
        assert result.all_healthy
        assert result.database.state == HealthState.HEALTHY
        assert result.memory.state == HealthState.HEALTHY

    def test_registered_check_overrides(self):
        dc = DependencyChecker()
        dc.register("database", lambda: ComponentHealth(name="database", state=HealthState.FAILED, error="no connection"))
        result = dc.check_all()
        assert not result.all_healthy
        assert result.database.state == HealthState.FAILED

    def test_to_dict(self):
        dc = DependencyChecker()
        d = dc.check_all().to_dict()
        assert "database" in d
        assert "memory" in d
        assert "model_router" in d
        assert "tool_gateway" in d
