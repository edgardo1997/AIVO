import math
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Optional


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    remaining: int
    retry_after: int = 0


class SlidingWindowRateLimiter:
    """Thread-safe, bounded sliding-window limiter using a monotonic clock."""

    def __init__(self, window_seconds: float = 60, max_buckets: int = 2048):
        if window_seconds <= 0 or max_buckets <= 0:
            raise ValueError("window_seconds and max_buckets must be positive")
        self._window = float(window_seconds)
        self._max_buckets = max_buckets
        self._buckets: Dict[str, Deque[float]] = {}
        self._lock = threading.RLock()

    def allow(
        self, key: str, *, limit: int, now: Optional[float] = None,
    ) -> RateLimitDecision:
        if limit <= 0:
            raise ValueError("limit must be positive")
        current = time.monotonic() if now is None else now
        cutoff = current - self._window

        with self._lock:
            self._evict_stale(cutoff)
            if key not in self._buckets and len(self._buckets) >= self._max_buckets:
                oldest_key = min(
                    self._buckets,
                    key=lambda bucket_key: self._buckets[bucket_key][-1],
                )
                del self._buckets[oldest_key]

            bucket = self._buckets.setdefault(key, deque())
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()

            if len(bucket) >= limit:
                retry_after = max(1, math.ceil(self._window - (current - bucket[0])))
                return RateLimitDecision(False, remaining=0, retry_after=retry_after)

            bucket.append(current)
            return RateLimitDecision(True, remaining=max(0, limit - len(bucket)))

    def clear(self) -> None:
        with self._lock:
            self._buckets.clear()

    def bucket_count(self) -> int:
        with self._lock:
            return len(self._buckets)

    def _evict_stale(self, cutoff: float) -> None:
        for key, bucket in list(self._buckets.items()):
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if not bucket:
                del self._buckets[key]
