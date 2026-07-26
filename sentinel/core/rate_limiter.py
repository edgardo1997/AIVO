"""Core rate limiter for Sentinel orchestrator.

Protects against runaway usage regardless of transport (FastAPI, CLI, etc.).
Provides sliding-window rate limiting per key (e.g. user_id, session_id, global).
Supports hierarchical checks across multiple tiers (global, user, session, tool).
Also provides a Token Bucket algorithm for burst control and user-tier differentiation.
"""

import math
import logging
import os
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    remaining: int
    retry_after: float = 0.0
    limit: int = 0
    tier: str = ""


DEFAULT_LIMITS: Dict[str, int] = {
    "global": 60,
    "user": 30,
    "session": 20,
}


TIER_LIMITS: Dict[str, Dict[str, int]] = {
    "free": {"global": 30, "user": 10, "session": 5},
    "premium": {"global": 200, "user": 100, "session": 50},
}


class TokenBucket:
    """Token Bucket rate limiter for burst control.

    Allows bursts up to `capacity` tokens, refilling at `rate` tokens per second.
    Thread-safe, monotic-clock based.
    """

    def __init__(self, capacity: float, rate: float):
        if capacity <= 0 or rate <= 0:
            raise ValueError("capacity and rate must be positive")
        self._capacity = float(capacity)
        self._rate = float(rate)
        self._tokens: Dict[str, float] = {}
        self._last_refill: Dict[str, float] = {}
        self._lock = __import__("threading").RLock()

    def allow(self, key: str, *, tokens: float = 1.0, now: Optional[float] = None) -> RateLimitDecision:
        current = time.monotonic() if now is None else now
        with self._lock:
            last = self._last_refill.get(key, current)
            elapsed = current - last
            self._tokens[key] = min(self._capacity, self._tokens.get(key, self._capacity) + elapsed * self._rate)
            self._last_refill[key] = current
            if self._tokens[key] >= tokens:
                self._tokens[key] -= tokens
                remaining_tokens = int(self._tokens[key])
                return RateLimitDecision(True, remaining=remaining_tokens, limit=int(self._capacity))
            deficit = tokens - self._tokens[key]
            retry_after = deficit / self._rate if self._rate > 0 else 0.0
            return RateLimitDecision(False, remaining=0, retry_after=math.ceil(retry_after), limit=int(self._capacity))

    def stats(self) -> Dict[str, object]:
        with self._lock:
            return {
                "type": "token_bucket",
                "capacity": self._capacity,
                "rate": self._rate,
                "active_keys": len(self._tokens),
            }


@dataclass
class ConsumptionRecord:
    timestamp: float
    key: str
    tier: str
    allowed: bool
    limit: int
    remaining: int


class ConsumptionTracker:
    """Tracks rate limit consumption for metrics and debugging."""

    def __init__(self, max_records: int = 10000):
        self._records: Deque[ConsumptionRecord] = deque(maxlen=max_records)
        self._lock = __import__("threading").RLock()

    def record(self, key: str, tier: str, allowed: bool, limit: int, remaining: int) -> None:
        with self._lock:
            self._records.append(ConsumptionRecord(time.time(), key, tier, allowed, limit, remaining))

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            total = len(self._records)
            denied = sum(1 for r in self._records if not r.allowed)
            by_tier: Dict[str, int] = defaultdict(int)
            for r in self._records:
                by_tier[r.tier] += 1
            return {
                "total_checks": total,
                "total_denied": denied,
                "denied_rate": round(denied / total * 100, 2) if total else 0.0,
                "checks_by_tier": dict(by_tier),
                "window_records": total,
            }


def user_tier_limits(user_tier: str = "free") -> Dict[str, int]:
    return dict(TIER_LIMITS.get(user_tier, TIER_LIMITS["free"]))


def make_error_json(message: str, retry_after: float = 0.0, tier: str = "") -> str:
    import json

    return json.dumps(
        {
            "error": "rate_limit_exceeded",
            "message": message,
            "retry_after_seconds": retry_after,
            "tier": tier,
        }
    )


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
        self._lock = __import__("threading").RLock()
        self._consumption = ConsumptionTracker()
        self._token_buckets: Dict[str, TokenBucket] = {}

    def register_token_bucket(self, name: str, capacity: float, rate: float) -> TokenBucket:
        tb = TokenBucket(capacity, rate)
        self._token_buckets[name] = tb
        return tb

    def token_bucket(self, name: str) -> Optional[TokenBucket]:
        return self._token_buckets.get(name)

    def allow(
        self,
        key: str,
        *,
        limit: int,
        now: Optional[float] = None,
        tier: str = "",
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
                dec = RateLimitDecision(False, remaining=0, retry_after=math.ceil(retry_after), limit=limit, tier=tier)
                self._consumption.record(key, tier, False, limit, 0)
                return dec

            bucket.append(current)
            remaining = max(0, limit - len(bucket))
            self._consumption.record(key, tier, True, limit, remaining)
            return RateLimitDecision(True, remaining=remaining, limit=limit, tier=tier)

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

    def check_hierarchy(
        self,
        tiers: List[Tuple[str, int]],
        *,
        now: Optional[float] = None,
        tier_label: str = "",
    ) -> RateLimitDecision:
        """Check and record against a hierarchy of rate limit tiers.

        Tiers are evaluated in order (most specific first is recommended).
        The first denied tier short-circuits and returns its decision.
        All tiers are recorded on success.

        Args:
            tiers: List of (key, limit) tuples, ordered by priority.
            tier_label: User tier label (e.g. "free", "premium") for tracking.

        Returns:
            RateLimitDecision for the first denied tier, or the last allowed tier.
        """
        last_allowed = RateLimitDecision(True, remaining=0)
        for key, limit in tiers:
            dec = self.allow(key, limit=limit, now=now, tier=tier_label)
            if not dec.allowed:
                return dec
            last_allowed = dec
        return last_allowed

    def consumption_summary(self) -> Dict[str, Any]:
        return self._consumption.summary()

    def clear(self) -> int:
        with self._lock:
            count = len(self._buckets)
            self._buckets.clear()
            return count

    def stats(self) -> Dict[str, object]:
        with self._lock:
            tb_stats = {name: tb.stats() for name, tb in self._token_buckets.items()}
            return {
                "window_seconds": self._window,
                "max_buckets": self._max_buckets,
                "active_keys": len(self._buckets),
                "limits": dict(DEFAULT_LIMITS),
                "tier_limits": dict(TIER_LIMITS),
                "token_buckets": tb_stats,
                "consumption": self.consumption_summary(),
            }

    def _evict_stale(self, cutoff: float) -> None:
        for key, bucket in list(self._buckets.items()):
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if not bucket:
                del self._buckets[key]


def load_rate_limit_config(path: str) -> Dict[str, int]:
    """Load rate limit configuration from YAML file, falling back to defaults.

    Expected YAML structure:
        global:
          requests_per_minute: 1000
        user:
          default: 100
        session:
          default: 50
        tiers:
          free:
            global: 30
            user: 10
            session: 5
          premium:
            global: 200
            user: 100
            session: 50
        tools:
          kb:
            requests_per_minute: 60
          filesystem:
            requests_per_minute: 30

    Returns a flat dict mapping tier keys to their limits.
    """
    if path and os.path.exists(path):
        try:
            import yaml

            with open(path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f)
            if not isinstance(raw, dict):
                return dict(DEFAULT_LIMITS)
            limits: Dict[str, int] = {}
            if "global" in raw:
                limits["global"] = int(raw["global"].get("requests_per_minute", DEFAULT_LIMITS.get("global", 1000)))
            if "user" in raw:
                limits["user"] = int(raw["user"].get("default", DEFAULT_LIMITS.get("user", 100)))
            if "session" in raw:
                limits["session"] = int(raw["session"].get("default", DEFAULT_LIMITS.get("session", 50)))
            if "tiers" in raw and isinstance(raw["tiers"], dict):
                for tier_name, tier_cfg in raw["tiers"].items():
                    for level, val in tier_cfg.items():
                        limits[f"tier:{tier_name}:{level}"] = int(val)
            if "tools" in raw and isinstance(raw["tools"], dict):
                for tool_cat, cfg in raw["tools"].items():
                    if isinstance(cfg, dict) and "requests_per_minute" in cfg:
                        limits[f"tool:{tool_cat}"] = int(cfg["requests_per_minute"])
            if limits:
                return limits
        except Exception:
            logger.debug("Rate-limit configuration load failed", exc_info=True)
    return dict(DEFAULT_LIMITS)
