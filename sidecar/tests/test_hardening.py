import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from sentinel.core.hardening import (
    HardeningConfig, HardeningService, ToolCircuitBreaker,
    TimeoutManager, EnhancedRetryHandler, HealthChecker,
)
from sentinel.core.recovery import ErrorCategory, RecoveryPolicy, RetryExhaustedError
from sentinel.core.tool import ToolResult


class TestHardeningConfig:
    def test_defaults(self):
        c = HardeningConfig()
        assert c.default_timeout_seconds == 30
        assert c.default_circuit_breaker_threshold == 3
        assert c.get_timeout("any.tool") == 30

    def test_tool_overrides(self):
        c = HardeningConfig(tool_overrides={
            "slow.tool": {"timeout_seconds": 120},
        })
        assert c.get_timeout("slow.tool") == 120
        assert c.get_timeout("other.tool") == 30
        assert c.get_circuit_breaker_threshold("slow.tool") == 3

    def test_to_dict(self):
        c = HardeningConfig(default_timeout_seconds=60)
        d = c.to_dict()
        assert d["default_timeout_seconds"] == 60


class TestToolCircuitBreaker:
    @pytest.fixture
    def cb(self):
        return ToolCircuitBreaker(failure_threshold=2, cooldown_seconds=0.1)

    def test_initial_state(self, cb):
        assert cb.allow_request("test.tool") is True

    def test_opens_after_threshold(self, cb):
        cb.record_failure("test.tool")
        cb.record_failure("test.tool")
        assert cb.allow_request("test.tool") is False

    def test_recovers_after_cooldown(self, cb):
        cb.record_failure("test.tool")
        cb.record_failure("test.tool")
        assert cb.allow_request("test.tool") is False
        import time
        time.sleep(0.15)
        assert cb.allow_request("test.tool") is True

    def test_success_resets(self, cb):
        cb.record_failure("test.tool")
        cb.record_success("test.tool")
        assert cb.allow_request("test.tool") is True
        state = cb.get_state("test.tool")
        assert state["consecutive_failures"] == 0

    def test_reset_all(self, cb):
        cb.record_failure("t1")
        cb.record_failure("t2")
        assert cb.reset() == 2
        assert cb.allow_request("t1") is True

    def test_get_all_states(self, cb):
        cb.record_failure("t1")
        states = cb.get_all_states()
        assert any(s["provider_id"] == "t1" for s in states)


class TestTimeoutManager:
    @pytest.fixture
    def mgr(self):
        return TimeoutManager(HardeningConfig(default_timeout_seconds=1))

    @pytest.mark.asyncio
    async def test_timeout_enforced(self, mgr):
        async def slow_fn():
            await asyncio.sleep(5)
            return ToolResult.ok(data="done")

        result = await mgr.execute(slow_fn, "slow.tool")
        assert not result.success
        assert "timed out" in result.error

    @pytest.mark.asyncio
    async def test_fast_fn_passes(self, mgr):
        async def fast_fn():
            return ToolResult.ok(data="done")

        result = await mgr.execute(fast_fn, "fast.tool", spec_timeout=10)
        assert result.success
        assert result.data == "done"


class TestEnhancedRetryHandler:
    @pytest.fixture
    def handler(self):
        return EnhancedRetryHandler()

    @pytest.mark.asyncio
    async def test_success_on_first_try(self, handler):
        fn = AsyncMock(return_value=ToolResult.ok(data="done"))
        result = await handler.execute(fn, RecoveryPolicy(max_retries=3), "test.tool", jitter=0.1)
        assert result.success
        fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_retries_on_transient(self, handler):
        call_count = 0

        async def flaky_fn():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return ToolResult.fail("timeout error")
            return ToolResult.ok(data="done")

        result = await handler.execute(flaky_fn, RecoveryPolicy(max_retries=3), "test.tool", jitter=0.1)
        assert result.success
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_raises_after_exhausted(self, handler):
        fn = AsyncMock(return_value=ToolResult.fail("timeout error"))
        with pytest.raises(RetryExhaustedError):
            await handler.execute(fn, RecoveryPolicy(max_retries=2), "test.tool", jitter=0.1)

    @pytest.mark.asyncio
    async def test_no_retry_on_functional(self, handler):
        fn = AsyncMock(return_value=ToolResult.fail("not found error"))
        result = await handler.execute(fn, RecoveryPolicy(max_retries=3), "test.tool", jitter=0.1)
        assert not result.success
        fn.assert_called_once()


class TestHardeningService:
    @pytest.fixture
    def svc(self):
        return HardeningService()

    def test_initial_stats(self, svc):
        stats = svc.stats()
        assert stats["timeouts"] == 0
        assert stats["circuit_breaker_blocks"] == 0
        assert stats["retries_attempted"] == 0

    def test_record_timeout(self, svc):
        svc.record_timeout()
        assert svc.stats()["timeouts"] == 1

    def test_record_circuit_block(self, svc):
        svc.record_circuit_block()
        assert svc.stats()["circuit_breaker_blocks"] == 1

    def test_record_retry(self, svc):
        svc.record_retry(success=True)
        stats = svc.stats()
        assert stats["retries_attempted"] == 1
        assert stats["retries_successful"] == 1

    def test_failure_categories_are_observable(self, svc):
        category = svc.classify_failure("permission denied", "executor.command")
        assert category == ErrorCategory.POLICY
        assert svc.stats()["failures_by_category"]["policy"] == 1
        assert svc.should_trip_circuit(category) is False

    def test_only_dependency_failures_trip_circuits(self, svc):
        assert svc.should_trip_circuit(ErrorCategory.TRANSIENT) is True
        assert svc.should_trip_circuit(ErrorCategory.FATAL) is True
        assert svc.should_trip_circuit(ErrorCategory.FUNCTIONAL) is False
        assert svc.should_trip_circuit(ErrorCategory.CIRCUIT_OPEN) is False

    def test_update_config(self, svc):
        svc.update_config(default_timeout_seconds=60)
        assert svc.config.default_timeout_seconds == 60

    def test_tool_override(self, svc):
        svc.set_tool_override("test.tool", timeout_seconds=120)
        assert svc.config.get_timeout("test.tool") == 120
        assert svc.get_tool_override("test.tool")["timeout_seconds"] == 120

    def test_remove_tool_override(self, svc):
        svc.set_tool_override("test.tool", timeout_seconds=120)
        assert svc.remove_tool_override("test.tool") is True
        assert svc.config.get_timeout("test.tool") == 30

    def test_check_health(self, svc):
        health = svc.check_health()
        assert "system" in health
        assert "tools" in health
        assert "stats" in health


class TestHealthChecker:
    @pytest.fixture
    def checker(self):
        return HealthChecker(ToolCircuitBreaker())

    def test_tool_healthy_by_default(self, checker):
        result = checker.check_tool_health("test.tool")
        assert result["healthy"] is True
        assert result["circuit_state"] == "closed"

    def test_tool_unhealthy_when_open(self, checker):
        cb = ToolCircuitBreaker(failure_threshold=1, cooldown_seconds=999)
        checker = HealthChecker(cb)
        cb.record_failure("bad.tool")
        result = checker.check_tool_health("bad.tool")
        assert result["healthy"] is False
        assert result["circuit_state"] == "open"
