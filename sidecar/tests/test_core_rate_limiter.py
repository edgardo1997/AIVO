"""Tests for sentinel.core.rate_limiter."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import time
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from sentinel.core.rate_limiter import RateLimiter, RateLimitDecision, DEFAULT_LIMITS


class TestRateLimiter:
    def test_allow_within_limit(self):
        rl = RateLimiter(window_seconds=60)
        d = rl.allow("key1", limit=5)
        assert d.allowed
        assert d.remaining == 4
        assert d.limit == 5

    def test_allow_exceeds_limit(self):
        rl = RateLimiter(window_seconds=60)
        now = 1000.0
        for _ in range(3):
            rl.allow("key2", limit=3, now=now)
        d = rl.allow("key2", limit=3, now=now)
        assert not d.allowed
        assert d.remaining == 0
        assert d.retry_after > 0

    def test_allow_window_slides(self):
        rl = RateLimiter(window_seconds=10)
        now = 1000.0
        for _ in range(3):
            rl.allow("key3", limit=3, now=now)
        d = rl.allow("key3", limit=3, now=now + 11)
        assert d.allowed
        assert d.remaining == 2

    def test_allow_multiple_keys_independent(self):
        rl = RateLimiter(window_seconds=60)
        now = 1000.0
        for _ in range(5):
            rl.allow("a", limit=5, now=now)
        d_a = rl.allow("a", limit=5, now=now)
        assert not d_a.allowed
        d_b = rl.allow("b", limit=5, now=now)
        assert d_b.allowed

    def test_check_without_recording(self):
        rl = RateLimiter(window_seconds=60)
        now = 1000.0
        rl.allow("k", limit=3, now=now)
        d = rl.check("k", limit=3, now=now)
        assert d.remaining == 2  # still 2 because only 1 recorded
        # verify no new record: second check should give same result
        assert rl.check("k", limit=3, now=now).remaining == 2

    def test_check_empty_key(self):
        rl = RateLimiter(window_seconds=60)
        d = rl.check("nonexistent", limit=10)
        assert d.allowed
        assert d.remaining == 10

    def test_invalid_limit_raises(self):
        rl = RateLimiter(window_seconds=60)
        with pytest.raises(ValueError, match="limit must be positive"):
            rl.allow("k", limit=0)
        with pytest.raises(ValueError, match="limit must be positive"):
            rl.check("k", limit=-1)

    def test_invalid_window_raises(self):
        with pytest.raises(ValueError):
            RateLimiter(window_seconds=0)
        with pytest.raises(ValueError):
            RateLimiter(max_buckets=0)

    def test_clear(self):
        rl = RateLimiter(window_seconds=60)
        now = 1000.0
        rl.allow("a", limit=5, now=now)
        rl.allow("b", limit=5, now=now)
        assert rl.clear() == 2
        assert rl.stats()["active_keys"] == 0

    def test_stats(self):
        rl = RateLimiter(window_seconds=30, max_buckets=100)
        rl.allow("x", limit=5)
        stats = rl.stats()
        assert stats["window_seconds"] == 30
        assert stats["max_buckets"] == 100
        assert stats["active_keys"] == 1
        assert "limits" in stats

    def test_evict_stale_on_allow(self):
        rl = RateLimiter(window_seconds=1)
        now = 1000.0
        rl.allow("evict_me", limit=5, now=now)
        assert rl.stats()["active_keys"] == 1
        rl.allow("other", limit=5, now=now + 2)
        assert rl.stats()["active_keys"] == 1

    def test_max_buckets_evicts_oldest(self):
        rl = RateLimiter(window_seconds=60, max_buckets=2)
        now = 1000.0
        rl.allow("k1", limit=5, now=now)
        rl.allow("k2", limit=5, now=now + 1)
        rl.allow("k3", limit=5, now=now + 2)
        # only 2 should remain
        assert rl.stats()["active_keys"] == 2

    def test_retry_after_accuracy(self):
        rl = RateLimiter(window_seconds=10)
        now = 1000.0
        for _ in range(3):
            rl.allow("burst", limit=3, now=now)
        d = rl.allow("burst", limit=3, now=now)
        assert not d.allowed
        # retry_after should be ~10 (oldest entry is at `now`, window=10)
        assert d.retry_after >= 9.0

    def test_concurrent_safety(self):
        import threading

        rl = RateLimiter(window_seconds=60)
        errors = []

        def hammer():
            try:
                for _ in range(50):
                    rl.allow("shared", limit=1000)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=hammer) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors


class TestRateLimiterIntegration:
    @pytest.mark.asyncio
    async def test_orchestrator_rate_limits_global(self):
        from sentinel.core.orchestrator import Orchestrator
        from sentinel.core.intent import IntentEngine
        from sentinel.core.tool_gateway import ToolGateway
        from sentinel.core.rate_limiter import RateLimiter

        gw = MagicMock(spec=ToolGateway)
        gw.execute = AsyncMock()

        rl = RateLimiter(window_seconds=60)
        global_limit = DEFAULT_LIMITS["global"]

        orch = Orchestrator(
            intent_engine=IntentEngine(),
            tool_gateway=gw,
            rate_limiter=rl,
        )
        # Fill the global bucket
        for _ in range(global_limit):
            rl.allow("global", limit=global_limit)

        result = await orch.process("hello")
        assert result.rate_limited
        assert "Rate limit exceeded" in (result.error or "")

    @pytest.mark.asyncio
    async def test_orchestrator_rate_limits_session(self):
        from sentinel.core.orchestrator import Orchestrator
        from sentinel.core.intent import IntentEngine
        from sentinel.core.tool_gateway import ToolGateway
        from sentinel.core.rate_limiter import RateLimiter

        gw = MagicMock(spec=ToolGateway)
        gw.execute = AsyncMock()

        rl = RateLimiter(window_seconds=60)
        session_limit = DEFAULT_LIMITS["session"]

        orch = Orchestrator(
            intent_engine=IntentEngine(),
            tool_gateway=gw,
            rate_limiter=rl,
        )
        # Fill the session bucket
        for _ in range(session_limit):
            rl.allow("session:test-sess", limit=session_limit)

        result = await orch.process("hello", session_id="test-sess")
        assert result.rate_limited
        assert "Session rate limit exceeded" in (result.error or "")

    @pytest.mark.asyncio
    async def test_orchestrator_without_rate_limiter(self):
        from sentinel.core.orchestrator import Orchestrator
        from sentinel.core.intent import IntentEngine
        from sentinel.core.tool_gateway import ToolGateway

        gw = MagicMock(spec=ToolGateway)
        gw.execute = AsyncMock()
        gw._capability_registry = MagicMock()
        gw._capability_registry.list_all = MagicMock(return_value=[])

        orch = Orchestrator(
            intent_engine=IntentEngine(),
            tool_gateway=gw,
            rate_limiter=None,
        )
        result = await orch.process("hello")
        assert not result.rate_limited

    @pytest.mark.asyncio
    async def test_orchestrator_allows_normal_request(self):
        from sentinel.core.orchestrator import Orchestrator
        from sentinel.core.intent import IntentEngine
        from sentinel.core.tool_gateway import ToolGateway
        from sentinel.core.rate_limiter import RateLimiter

        gw = MagicMock(spec=ToolGateway)
        gw.execute = AsyncMock()
        gw._capability_registry = MagicMock()
        gw._capability_registry.list_all = MagicMock(return_value=[])
        gw.list_active = MagicMock(return_value=[])

        rl = RateLimiter(window_seconds=60)
        orch = Orchestrator(
            intent_engine=IntentEngine(),
            tool_gateway=gw,
            rate_limiter=rl,
        )
        result = await orch.process("hello")
        assert not result.rate_limited


class TestRateLimiterAPI:
    def setup_method(self):
        from modules.sentinel_bridge import reset_bridge

        reset_bridge()

    def test_rate_limiter_stats(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        resp = client.get("/api/sentinel/rate-limiter/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "enabled" in data

    def test_rate_limiter_clear(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        resp = client.post("/api/sentinel/rate-limiter/clear")
        assert resp.status_code == 200
        data = resp.json()
        assert "cleared" in data
