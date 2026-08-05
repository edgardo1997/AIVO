"""Tests for OAuth rate limiting."""

import time

import pytest

from services.rate_limiter import RateLimiter


class TestOAuthRateLimit:
    def test_excessive_start_rejected(self):
        limiter = RateLimiter(limits={"start": (3, 60)})
        for _ in range(3):
            assert limiter.allow("start", "user-1", "google")
        assert not limiter.allow("start", "user-1", "google")

    def test_different_users_isolated(self):
        limiter = RateLimiter(limits={"start": (3, 60)})
        for _ in range(3):
            assert limiter.allow("start", "user-a", "google")
        for _ in range(3):
            assert limiter.allow("start", "user-b", "google")

    def test_providers_isolated(self):
        limiter = RateLimiter(limits={"start": (3, 60)})
        for _ in range(3):
            assert limiter.allow("start", "user-1", "google")
        assert not limiter.allow("start", "user-1", "google")
        for _ in range(3):
            assert limiter.allow("start", "user-1", "microsoft")

    def test_window_expiration_restores_access(self):
        limiter = RateLimiter(limits={"start": (1, 1)})
        assert limiter.allow("start", "user-1", "google")
        assert not limiter.allow("start", "user-1", "google")
        time.sleep(1.1)
        assert limiter.allow("start", "user-1", "google")
