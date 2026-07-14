"""Core rate limiter for Sentinel orchestrator.

Protects against runaway usage regardless of transport (FastAPI, CLI, etc.).
Provides sliding-window rate limiting per key (e.g. user_id, session_id, global).
"""

import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Optional


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    remaining: int
    retry_after: float = 0.0
    limit: int = 0


DEFAULT_LIMITS: Dict[str, int] = {
    "global": 60,
    "user": 30,
    "session": 20,
}


class RateLimiter:
    """Sliding-window rate limiter, thread-safe, backed by monotonic clock.

    Limits are expressed as *max requests per window_seconds*.
    """

    def __init__(self, window_seconds: float = 60.0, max_buckets: int = 4096):
        if window_seconds <= 0 or max_buckets <= 0:
            raise ValueError("window_seconds and max_buckets must be positive")
        self._window = float(window_seconds)
        self._max_buckets = max_buckets
        self._buckets: Dict[str, Deque[float]] = {}
        self._lock = threading.RLock()

    def allow(
        self, key: str, *, limit: int, now: Optional[float] = None,
    ) -> RateLimitDecision:
        """Check and record a request for *key*. Returns the decision."""
        if limit <= 0:
            raise ValueError("limit must be positive")
        current = time.monotonic() if now is None else now
        cutoff = current - self._window

        with self._lock:
            self._evict_stale(cutoff)
            if key not in self._buckets and len(self._buckets) >= self._max_buckets:
                oldest_key = min(
                    self._buckets,
                    key=lambda k: self._buckets[k][-1],
                )
                del self._buckets[oldest_key]

            bucket = self._buckets.setdefault(key, deque())
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()

            if len(bucket) >= limit:
                retry_after = max(0.0, self._window - (current - bucket[0]))
                return RateLimitDecision(False, remaining=0, retry_after=math.ceil(retry_after), limit=limit)

            bucket.append(current)
            return RateLimitDecision(True, remaining=max(0, limit - len(bucket)), limit=limit)

    def check(self, key: str, *, limit: int, now: Optional[float] = None) -> RateLimitDecision:
        """Check without recording. Useful for inspection."""
        if limit <= 0:
            raise ValueError("limit must be positive")
        current = time.monotonic() if now is None else now
        cutoff = current - self._window

        with self._lock:
            bucket = self._buckets.get(key)
            if not bucket:
                return RateLimitDecision(True, remaining=limit, limit=limit)

            while bucket and bucket[0] <= cutoff:
                bucket.popleft()

            if len(bucket) >= limit:
                retry_after = max(0.0, self._window - (current - bucket[0]))
                return RateLimitDecision(False, remaining=0, retry_after=math.ceil(retry_after), limit=limit)
            return RateLimitDecision(True, remaining=max(0, limit - len(bucket)), limit=limit)

    def clear(self) -> int:
        with self._lock:
            count = len(self._buckets)
            self._buckets.clear()
            return count

    def stats(self) -> Dict[str, object]:
        with self._lock:
            return {
                "window_seconds": self._window,
                "max_buckets": self._max_buckets,
                "active_keys": len(self._buckets),
                "limits": dict(DEFAULT_LIMITS),
            }

    def _evict_stale(self, cutoff: float) -> None:
        for key, bucket in list(self._buckets.items()):
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if not bucket:
                del self._buckets[key]
