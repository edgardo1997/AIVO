import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import pytest
from sentinel.core.recovery import (
    ErrorCategory,
    ErrorClassifier,
    RecoveryPolicy,
    RetryHandler,
    FallbackHandler,
    RollbackManager,
    RetryExhaustedError,
)
from sentinel.core.planner import PlanStep


class TestErrorClassifier:
    def test_classify_transient_timeout(self):
        assert ErrorClassifier.classify("timeout after 30s") == ErrorCategory.TRANSIENT

    def test_classify_transient_rate_limit(self):
        assert ErrorClassifier.classify("rate limit exceeded") == ErrorCategory.TRANSIENT

    def test_classify_transient_connection(self):
        assert ErrorClassifier.classify("connection refused") == ErrorCategory.TRANSIENT

    def test_classify_transient_service(self):
        assert ErrorClassifier.classify("service unavailable") == ErrorCategory.TRANSIENT

    def test_classify_transient_http(self):
        assert ErrorClassifier.classify("HTTP 503") == ErrorCategory.TRANSIENT

    def test_classify_functional_not_found(self):
        assert ErrorClassifier.classify("tool not found") == ErrorCategory.FUNCTIONAL

    def test_classify_policy_denied(self):
        assert ErrorClassifier.classify("permission denied") == ErrorCategory.POLICY

    def test_classify_policy_requires_confirm(self):
        assert ErrorClassifier.classify("requires confirmation") == ErrorCategory.POLICY

    def test_classify_circuit_open(self):
        assert ErrorClassifier.classify("tool is circuit-open") == ErrorCategory.CIRCUIT_OPEN

    def test_classify_fatal_unknown(self):
        assert ErrorClassifier.classify("internal error: something broke") == ErrorCategory.FATAL

    def test_classify_empty_returns_fatal(self):
        assert ErrorClassifier.classify("") == ErrorCategory.FATAL

    def test_classify_none_tool_id(self):
        assert ErrorClassifier.classify("denied", "executor.command") == ErrorCategory.POLICY


class TestRecoveryPolicy:
    def test_default_for_ai(self):
        p = RecoveryPolicy.default_for("ai.chat")
        assert p.max_retries == 3
        assert "transient" in p.retry_on
        assert "ai.chat" in p.fallback_tool_ids

    def test_default_for_executor(self):
        p = RecoveryPolicy.default_for("executor.command")
        assert p.max_retries == 1
        assert "transient" in p.retry_on
        assert p.fallback_tool_ids == []

    def test_default_for_system(self):
        p = RecoveryPolicy.default_for("system.cpu")
        assert p.max_retries == 2

    def test_default_for_filesystem(self):
        p = RecoveryPolicy.default_for("filesystem.read")
        assert p.max_retries == 2

    def test_default_for_unknown(self):
        p = RecoveryPolicy.default_for("custom.tool")
        assert p.max_retries == 3


class FakeResult:
    def __init__(self, success, error=None, data=None, duration_ms=None):
        self.success = success
        self.error = error
        self.data = data
        self.duration_ms = duration_ms


class TestRetryHandler:
    @pytest.mark.asyncio
    async def test_success_first_attempt(self):
        handler = RetryHandler()
        call_count = 0

        async def fn():
            nonlocal call_count
            call_count += 1
            return FakeResult(success=True)

        result = await handler.execute(fn, RecoveryPolicy(max_retries=3), "test.tool")
        assert result.success is True
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_transient_then_success(self):
        handler = RetryHandler()
        call_count = 0

        async def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return FakeResult(success=False, error="timeout")
            return FakeResult(success=True)

        result = await handler.execute(
            fn,
            RecoveryPolicy(max_retries=3, retry_delay_ms=10),
            "test.tool",
        )
        assert result.success is True
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_exhausted_raises(self):
        handler = RetryHandler()
        call_count = 0

        async def fn():
            nonlocal call_count
            call_count += 1
            return FakeResult(success=False, error="timeout")

        with pytest.raises(RetryExhaustedError) as exc:
            await handler.execute(
                fn,
                RecoveryPolicy(max_retries=2, retry_delay_ms=10),
                "test.tool",
            )
        assert "test.tool" in str(exc.value)
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_no_retry_on_functional_error(self):
        handler = RetryHandler()
        call_count = 0

        async def fn():
            nonlocal call_count
            call_count += 1
            return FakeResult(success=False, error="not found")

        result = await handler.execute(
            fn,
            RecoveryPolicy(max_retries=3, retry_delay_ms=10),
            "test.tool",
        )
        assert result.success is False
        assert "not found" in (result.error or "")
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_no_retry_on_fatal_error(self):
        handler = RetryHandler()
        call_count = 0

        async def fn():
            nonlocal call_count
            call_count += 1
            return FakeResult(success=False, error="internal error")

        result = await handler.execute(
            fn,
            RecoveryPolicy(max_retries=3, retry_delay_ms=10),
            "test.tool",
        )
        assert result.success is False
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_transient_exception(self):
        handler = RetryHandler()
        call_count = 0

        async def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("timeout")
            return FakeResult(success=True)

        result = await handler.execute(
            fn,
            RecoveryPolicy(max_retries=3, retry_delay_ms=10),
            "test.tool",
        )
        assert result.success is True
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_fatal_exception_not_retried(self):
        handler = RetryHandler()
        call_count = 0

        async def fn():
            nonlocal call_count
            call_count += 1
            raise ValueError("internal error")

        with pytest.raises(ValueError):
            await handler.execute(
                fn,
                RecoveryPolicy(max_retries=3, retry_delay_ms=10),
                "test.tool",
            )
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_backoff_delay_increases(self):
        handler = RetryHandler()
        delays = []
        original_sleep = asyncio.sleep

        async def tracking_sleep(delay):
            delays.append(delay)
            await original_sleep(0)

        asyncio.sleep = tracking_sleep
        try:
            call_count = 0

            async def fn():
                nonlocal call_count
                call_count += 1
                return FakeResult(success=False, error="timeout")

            with pytest.raises(RetryExhaustedError):
                await handler.execute(
                    fn,
                    RecoveryPolicy(max_retries=3, retry_delay_ms=100, retry_backoff=2.0, retry_max_delay_ms=10000),
                    "test.tool",
                )
            assert len(delays) == 2
            assert abs(delays[0] - 0.1) < 0.01
            assert abs(delays[1] - 0.2) < 0.01
        finally:
            asyncio.sleep = original_sleep

    @pytest.mark.asyncio
    async def test_retry_max_delay_capped(self):
        handler = RetryHandler()
        delays = []
        original_sleep = asyncio.sleep

        async def tracking_sleep(delay):
            delays.append(delay)
            await original_sleep(0)

        asyncio.sleep = tracking_sleep
        try:
            call_count = 0

            async def fn():
                nonlocal call_count
                call_count += 1
                return FakeResult(success=False, error="timeout")

            with pytest.raises(RetryExhaustedError):
                await handler.execute(
                    fn,
                    RecoveryPolicy(max_retries=4, retry_delay_ms=1000, retry_backoff=5.0, retry_max_delay_ms=3000),
                    "test.tool",
                )
            assert len(delays) == 3
            assert delays[2] <= 3.0
        finally:
            asyncio.sleep = original_sleep


class TestFallbackHandler:
    @pytest.mark.asyncio
    async def test_success_returns_original(self):
        handler = FallbackHandler()
        result = await handler.execute(
            FakeResult(success=True),
            [lambda: FakeResult(success=True)],
            RecoveryPolicy(fallback_tool_ids=["alt"]),
            "test.tool",
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_functional_error_triggers_fallback(self):
        handler = FallbackHandler()
        call_count = [0]

        async def fb():
            call_count[0] += 1
            return FakeResult(success=True)

        result = await handler.execute(
            FakeResult(success=False, error="not found"),
            [fb],
            RecoveryPolicy(fallback_tool_ids=["alt"]),
            "test.tool",
        )
        assert result.success is True
        assert call_count[0] == 1

    @pytest.mark.asyncio
    async def test_fallback_first_wins(self):
        handler = FallbackHandler()
        calls = []

        async def fb1():
            calls.append("fb1")
            return FakeResult(success=False, error="not found")

        async def fb2():
            calls.append("fb2")
            return FakeResult(success=True, error=None)

        result = await handler.execute(
            FakeResult(success=False, error="not found"),
            [fb1, fb2],
            RecoveryPolicy(fallback_tool_ids=["alt1", "alt2"]),
            "test.tool",
        )
        assert result.success is True
        assert calls == ["fb1", "fb2"]

    @pytest.mark.asyncio
    async def test_transient_error_does_not_trigger_fallback(self):
        handler = FallbackHandler()
        call_count = [0]

        async def fb():
            call_count[0] += 1
            return FakeResult(success=True)

        result = await handler.execute(
            FakeResult(success=False, error="timeout"),
            [fb],
            RecoveryPolicy(fallback_tool_ids=["alt"]),
            "test.tool",
        )
        assert result.success is False
        assert call_count[0] == 0

    @pytest.mark.asyncio
    async def test_empty_fallback_list_returns_original(self):
        handler = FallbackHandler()
        result = await handler.execute(
            FakeResult(success=False, error="not found"),
            [],
            RecoveryPolicy(fallback_tool_ids=[]),
            "test.tool",
        )
        assert result.success is False

    @pytest.mark.asyncio
    async def test_all_fallbacks_fail_returns_original(self):
        handler = FallbackHandler()

        async def fb():
            return FakeResult(success=False, error="still denied")

        result = await handler.execute(
            FakeResult(success=False, error="not found"),
            [fb, fb],
            RecoveryPolicy(fallback_tool_ids=["alt1", "alt2"]),
            "test.tool",
        )
        assert result.success is False
        assert result.error == "not found"

    @pytest.mark.asyncio
    async def test_policy_error_never_triggers_fallback(self):
        handler = FallbackHandler()
        called = [False]

        async def fb():
            called[0] = True
            return FakeResult(success=True)

        original = FakeResult(success=False, error="blocked by policy")
        result = await handler.execute(
            original,
            [fb],
            RecoveryPolicy(fallback_tool_ids=["alt"]),
            "test.tool",
        )
        assert result is original
        assert called[0] is False

    @pytest.mark.asyncio
    async def test_fallback_exception_logged_continues(self):
        handler = FallbackHandler()
        calls = []

        async def fb1():
            calls.append("fb1")
            raise RuntimeError("crash")

        async def fb2():
            calls.append("fb2")
            return FakeResult(success=True)

        result = await handler.execute(
            FakeResult(success=False, error="not found"),
            [fb1, fb2],
            RecoveryPolicy(fallback_tool_ids=["alt1", "alt2"]),
            "test.tool",
        )
        assert result.success is True
        assert calls == ["fb1", "fb2"]


class TestRollbackManager:
    @pytest.mark.asyncio
    async def test_no_reversible_steps_returns_empty(self):
        rm = RollbackManager()
        step = PlanStep(id="s1", tool_id="test.tool", description="", is_reversible=False)
        result = FakeResult(success=True, error=None)
        actions = await rm.rollback([(step, result)], lambda tid, p: FakeResult(success=True))
        assert actions == []

    @pytest.mark.asyncio
    async def test_reversible_step_triggers_rollback(self):
        rm = RollbackManager()
        step = PlanStep(id="s1", tool_id="test.tool", description="", is_reversible=True, rollback_tool_id="undo.tool")
        result = FakeResult(success=True, error=None)
        calls = []

        async def rb(tid, p):
            calls.append((tid, p))
            return FakeResult(success=True)

        actions = await rm.rollback([(step, result)], rb)
        assert len(actions) == 1
        assert actions[0].success is True
        assert actions[0].rollback_tool_id == "undo.tool"
        assert calls == [("undo.tool", {})]

    @pytest.mark.asyncio
    async def test_rollback_reverse_order(self):
        rm = RollbackManager()
        steps = [
            PlanStep(id="s1", tool_id="a", is_reversible=True, rollback_tool_id="undo.a"),
            PlanStep(id="s2", tool_id="b", is_reversible=True, rollback_tool_id="undo.b"),
        ]
        order = []

        async def rb(tid, p):
            order.append(tid)
            return FakeResult(success=True)

        await rm.rollback([(s, FakeResult(success=True)) for s in steps], rb)
        assert order == ["undo.b", "undo.a"]

    @pytest.mark.asyncio
    async def test_rollback_only_reversible(self):
        rm = RollbackManager()
        steps = [
            PlanStep(id="s1", tool_id="a", is_reversible=True, rollback_tool_id="undo.a"),
            PlanStep(id="s2", tool_id="b", is_reversible=False),
        ]
        calls = []

        async def rb(tid, p):
            calls.append(tid)
            return FakeResult(success=True)

        actions = await rm.rollback([(s, FakeResult(success=True)) for s in steps], rb)
        assert len(actions) == 1
        assert actions[0].tool_id == "a"

    @pytest.mark.asyncio
    async def test_rollback_params_from_step(self):
        rm = RollbackManager()
        step = PlanStep(
            id="s1",
            tool_id="test.tool",
            description="",
            is_reversible=True,
            rollback_tool_id="undo.tool",
            rollback_params={"key": "val"},
        )
        calls = []

        async def rb(tid, p):
            calls.append((tid, p))
            return FakeResult(success=True)

        await rm.rollback([(step, FakeResult(success=True))], rb)
        assert calls[0][1] == {"key": "val"}

    @pytest.mark.asyncio
    async def test_rollback_params_from_result_data(self):
        rm = RollbackManager()
        step = PlanStep(id="s1", tool_id="test.tool", description="", is_reversible=True, rollback_tool_id="undo.tool")
        result = FakeResult(success=True, data={"pid": 42})
        calls = []

        async def rb(tid, p):
            calls.append((tid, p))
            return FakeResult(success=True)

        await rm.rollback([(step, result)], rb)
        assert calls[0][1] == {"pid": 42}

    @pytest.mark.asyncio
    async def test_rollback_failure_logged_continues(self):
        rm = RollbackManager()
        steps = [
            PlanStep(id="s1", tool_id="a", is_reversible=True, rollback_tool_id="undo.a"),
            PlanStep(id="s2", tool_id="b", is_reversible=True, rollback_tool_id="undo.b"),
        ]
        call_order = []

        async def rb(tid, p):
            call_order.append(tid)
            if tid == "undo.b":
                return FakeResult(success=False, error="rollback failed")
            return FakeResult(success=True)

        actions = await rm.rollback([(s, FakeResult(success=True)) for s in steps], rb)
        assert len(actions) == 2
        assert actions[0].success is False
        assert actions[1].success is True

    @pytest.mark.asyncio
    async def test_rollback_exception_continues(self):
        rm = RollbackManager()
        steps = [
            PlanStep(id="s1", tool_id="a", is_reversible=True, rollback_tool_id="undo.a"),
            PlanStep(id="s2", tool_id="b", is_reversible=True, rollback_tool_id="undo.b"),
        ]
        call_order = []

        async def rb(tid, p):
            call_order.append(tid)
            if tid == "undo.b":
                raise RuntimeError("crash")
            return FakeResult(success=True)

        actions = await rm.rollback([(s, FakeResult(success=True)) for s in steps], rb)
        assert len(actions) == 2
        assert actions[0].success is False
        assert "crash" in (actions[0].error or "")
        assert actions[1].success is True


class TestRecoveryPolicyInPlanner:
    def test_step_definitions_have_recovery_policy(self):
        from sentinel.core.planner import STEP_DEFINITIONS, PlanStep

        for tool_id, steps in STEP_DEFINITIONS.items():
            for step in steps:
                assert hasattr(step, "recovery_policy"), f"{tool_id}.{step.id} missing recovery_policy"

    def test_plan_steps_get_default_recovery(self):
        from sentinel.core import Intent, Planner

        planner = Planner()
        intent = Intent(action="query", target="system.cpu", parameters={}, confidence=1.0, raw_input="cpu")
        plan = planner.plan(intent)
        for step in plan.steps:
            assert step.recovery_policy is not None, f"{step.id} has no recovery_policy"
            assert step.recovery_policy.max_retries == 2
