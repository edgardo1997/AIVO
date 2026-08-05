"""In-memory rate limiters for Sentinel endpoints.

OAuth limiter is per owner (user/session) and provider. IP is not used because
all traffic originates from 127.0.0.1.

SlidingWindowRateLimiter is a generic per-key, per-path sliding window limiter
used by the main sidecar middleware.
"""

import logging
import time
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock
from typing import Dict, Optional, Tuple

logger = logging.getLogger("sentinel.rate_limit")


class Clock(ABC):
    """Deterministic clock abstraction for testing and production."""

    @abstractmethod
    def now(self) -> float:
        ...


class MonotonicClock(Clock):
    def now(self) -> float:
        return time.monotonic()


class FakeClock(Clock):
    def __init__(self, t: float = 0.0):
        self.t = t

    def now(self) -> float:
        return self.t

    def set(self, t: float) -> None:
        self.t = t


class RateLimiter:
    """OAuth-aware rate limiter."""

    def __init__(self, limits: Dict[str, Tuple[int, int]] | None = None):
        # key: (action, owner_id, provider) -> list of timestamps
        self._windows: Dict[Tuple[str, str, str], list[float]] = defaultdict(list)
        self._lock = Lock()
        self._limits = limits or {
            "start": (5, 60),     # 5 starts per 60s
            "poll": (30, 60),     # 30 polls per 60s
            "cancel": (5, 60),    # 5 cancels per 60s
            "callback_failure": (10, 60),
        }

    def _prune(self, timestamps: list[float], window: int) -> list[float]:
        now = time.time()
        return [t for t in timestamps if now - t < window]

    def allow(self, action: str, owner_id: str, provider: str) -> bool:
        key = (action, owner_id, provider)
        limit, window = self._limits.get(action, (10, 60))
        with self._lock:
            self._windows[key] = self._prune(self._windows[key], window)
            if len(self._windows[key]) >= limit:
                logger.warning("Rate limit hit: action=%s owner=%s provider=%s", action, owner_id, provider)
                return False
            self._windows[key].append(time.time())
            return True


@dataclass
class Decision:
    allowed: bool
    remaining: int
    retry_after: float


class SlidingWindowRateLimiter:
    """Generic per-key sliding window rate limiter."""

    def __init__(
        self,
        window_seconds: int = 60,
        max_buckets: int = 1024,
        clock: Optional[Clock] = None,
    ):
        self._window = window_seconds
        self._max_buckets = max_buckets
        self._buckets: Dict[str, deque[float]] = {}
        self._lock = Lock()
        self._clock = clock or MonotonicClock()

    def allow(self, key: str, limit: int, *, now: float | None = None) -> Decision:
        if now is None:
            now = self._clock.now()
        with self._lock:
            if key not in self._buckets and len(self._buckets) >= self._max_buckets:
                # prune stale buckets to make room
                stale = [
                    k for k, b in self._buckets.items()
                    if b and now - b[0] >= self._window
                ]
                for k in stale:
                    del self._buckets[k]
                if len(self._buckets) >= self._max_buckets:
                    # fallback: drop least-recently-used
                    lru = min(self._buckets, key=lambda k: self._buckets[k][-1])
                    del self._buckets[lru]
            bucket = self._buckets.setdefault(key, deque())
            while bucket and now - bucket[0] >= self._window:
                bucket.popleft()
            if len(bucket) >= limit:
                logger.warning("Rate limit hit: key=%s limit=%d", key, limit)
                retry_after = max(0.0, self._window - (now - bucket[0])) if bucket else float(self._window)
                return Decision(allowed=False, remaining=0, retry_after=retry_after)
            bucket.append(now)
            return Decision(allowed=True, remaining=limit - len(bucket), retry_after=0.0)

    def bucket_count(self) -> int:
        with self._lock:
            return len(self._buckets)

    def clear(self) -> None:
        with self._lock:
            self._buckets.clear()
