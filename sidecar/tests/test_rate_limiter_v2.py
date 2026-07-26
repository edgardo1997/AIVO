"""Tests for Token Bucket, user tier support, and consumption tracking."""

import math
import time
import pytest

from sentinel.core.rate_limiter import (
    RateLimiter,
    TokenBucket,
    ConsumptionTracker,
    user_tier_limits,
    TIER_LIMITS,
)


class TestTokenBucket:
    @pytest.mark.unit
    def test_allows_burst(self):
        bucket = TokenBucket(capacity=10, rate=5.0)
        for _ in range(10):
            dec = bucket.allow("test")
            assert dec.allowed

    @pytest.mark.unit
    def test_blocks_excess(self):
        bucket = TokenBucket(capacity=3, rate=1.0)
        for _ in range(3):
            assert bucket.allow("test").allowed
        dec = bucket.allow("test")
        assert not dec.allowed
        assert dec.retry_after > 0

    @pytest.mark.unit
    def test_refills(self):
        bucket = TokenBucket(capacity=5, rate=10.0)
        for _ in range(5):
            assert bucket.allow("test").allowed
        dec = bucket.allow("test")
        assert not dec.allowed
        time.sleep(0.15)
        dec = bucket.allow("test", now=time.monotonic())
        assert dec.allowed

    @pytest.mark.unit
    def test_multiple_keys_independent(self):
        bucket = TokenBucket(capacity=2, rate=5.0)
        assert bucket.allow("user_a").allowed
        assert bucket.allow("user_a").allowed
        assert not bucket.allow("user_a").allowed
        assert bucket.allow("user_b").allowed

    @pytest.mark.unit
    def test_invalid_params(self):
        with pytest.raises(ValueError):
            TokenBucket(capacity=0, rate=1.0)
        with pytest.raises(ValueError):
            TokenBucket(capacity=1, rate=0)

    @pytest.mark.unit
    def test_stats(self):
        bucket = TokenBucket(capacity=10, rate=5.0)
        stats = bucket.stats()
        assert stats["type"] == "token_bucket"
        assert stats["capacity"] == 10
        assert stats["rate"] == 5.0


class TestUserTierLimits:
    @pytest.mark.unit
    def test_free_tier_limits(self):
        limits = user_tier_limits("free")
        assert limits["global"] == 30
        assert limits["user"] == 10
        assert limits["session"] == 5

    @pytest.mark.unit
    def test_premium_tier_limits(self):
        limits = user_tier_limits("premium")
        assert limits["global"] == 200
        assert limits["user"] == 100
        assert limits["session"] == 50

    @pytest.mark.unit
    def test_unknown_tier_falls_back_to_free(self):
        limits = user_tier_limits("unknown_tier")
        assert limits["global"] == 30

    @pytest.mark.unit
    def test_tier_limits_structure(self):
        assert "free" in TIER_LIMITS
        assert "premium" in TIER_LIMITS
        for tier in ("free", "premium"):
            for key in ("global", "user", "session"):
                assert key in TIER_LIMITS[tier]


class TestConsumptionTracker:
    @pytest.mark.unit
    def test_records_consumption(self):
        tracker = ConsumptionTracker(max_records=100)
        tracker.record("user:abc", "free", True, 30, 25)
        tracker.record("global", "free", False, 30, 0)
        summary = tracker.summary()
        assert summary["total_checks"] == 2
        assert summary["total_denied"] == 1

    @pytest.mark.unit
    def test_empty_summary(self):
        tracker = ConsumptionTracker()
        summary = tracker.summary()
        assert summary["total_checks"] == 0
        assert summary["total_denied"] == 0

    @pytest.mark.unit
    def test_checks_by_tier(self):
        tracker = ConsumptionTracker()
        tracker.record("k1", "free", True, 10, 5)
        tracker.record("k2", "premium", True, 50, 40)
        summary = tracker.summary()
        assert summary["checks_by_tier"]["free"] == 1
        assert summary["checks_by_tier"]["premium"] == 1


class TestRateLimiterIntegration:
    @pytest.mark.unit
    def test_hierarchy_with_tier(self):
        limiter = RateLimiter(window_seconds=60.0)
        dec = limiter.check_hierarchy([("global", 1000), ("user:test", 100)], tier_label="premium")
        assert dec.allowed

    @pytest.mark.unit
    def test_token_bucket_registration(self):
        limiter = RateLimiter()
        tb = limiter.register_token_bucket("burst_control", capacity=10, rate=5.0)
        assert tb is not None
        assert limiter.token_bucket("burst_control") is tb

    @pytest.mark.unit
    def test_consumption_summary(self):
        limiter = RateLimiter()
        limiter.allow("test_key", limit=100, tier="free")
        limiter.allow("test_key", limit=100, tier="free")
        summary = limiter.consumption_summary()
        assert summary["total_checks"] == 2

    @pytest.mark.unit
    def test_stats_includes_tier_info(self):
        limiter = RateLimiter()
        stats = limiter.stats()
        assert "tier_limits" in stats
        assert "token_buckets" in stats
        assert "consumption" in stats

    @pytest.mark.unit
    def test_denied_rate_limit(self):
        limiter = RateLimiter(window_seconds=3600.0)
        for _ in range(3):
            limiter.allow("limited_key", limit=3, tier="free")
        dec = limiter.allow("limited_key", limit=3, tier="free")
        assert not dec.allowed
        assert dec.tier == "free"
