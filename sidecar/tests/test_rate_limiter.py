from concurrent.futures import ThreadPoolExecutor

from services.rate_limiter import SlidingWindowRateLimiter


def test_limit_boundary_and_retry_after():
    limiter = SlidingWindowRateLimiter(window_seconds=60)
    assert limiter.allow("actor:route", limit=2, now=100).allowed is True
    assert limiter.allow("actor:route", limit=2, now=101).allowed is True
    denied = limiter.allow("actor:route", limit=2, now=102)
    assert denied.allowed is False
    assert denied.retry_after == 58
    assert limiter.allow("actor:route", limit=2, now=161).allowed is True


def test_bucket_store_is_bounded():
    limiter = SlidingWindowRateLimiter(window_seconds=60, max_buckets=3)
    for index in range(10):
        assert limiter.allow(f"actor-{index}", limit=1, now=float(index)).allowed
    assert limiter.bucket_count() == 3


def test_concurrent_requests_cannot_exceed_limit():
    limiter = SlidingWindowRateLimiter(window_seconds=60)

    def attempt(_):
        return limiter.allow("shared", limit=25, now=100).allowed

    with ThreadPoolExecutor(max_workers=16) as pool:
        decisions = list(pool.map(attempt, range(100)))
    assert sum(decisions) == 25
