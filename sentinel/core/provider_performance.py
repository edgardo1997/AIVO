"""Bounded, privacy-safe provider performance intelligence.

This module is the authoritative source of recent provider/model performance
for soft routing.  It stores only non-sensitive operational timing and outcome
metadata.  No prompt text, response text, API keys, user identity, filesystem
paths or conversation content is retained.
"""

from __future__ import annotations
import math
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class ProviderPerformanceObservation:
    """One operational measurement of a provider/model execution.

    Owner: sentinel.core.provider_performance.ProviderPerformanceStore
    Producer: ProviderManager or ModelRouter after a request finishes/fails
    Consumers: ProviderSelector (soft score), telemetry, audit
    Retention: bounded in-memory rolling history; no persistence by default
    Privacy: no prompt/response text, no keys, no identity, no paths
    Failure behavior: missing data yields neutral 0.5 performance score
    """

    provider_id: str
    model_id: str
    timestamp: float = field(default_factory=time.monotonic)
    connection_ms: Optional[float] = None
    headers_ms: Optional[float] = None
    ttft_ms: Optional[float] = None
    generation_ms: Optional[float] = None
    output_tokens: int = 0
    generation_tokens_per_second: float = 0.0
    total_provider_ms: float = 0.0
    success: bool = True
    timeout: bool = False
    cancelled: bool = False
    fallback_triggered: bool = False
    error_category: Optional[str] = None
    estimated_cost: float = 0.0
    correlation_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "timestamp": self.timestamp,
            "connection_ms": self.connection_ms,
            "headers_ms": self.headers_ms,
            "ttft_ms": self.ttft_ms,
            "generation_ms": self.generation_ms,
            "output_tokens": self.output_tokens,
            "generation_tokens_per_second": self.generation_tokens_per_second,
            "total_provider_ms": self.total_provider_ms,
            "success": self.success,
            "timeout": self.timeout,
            "cancelled": self.cancelled,
            "fallback_triggered": self.fallback_triggered,
            "error_category": self.error_category,
            "estimated_cost": self.estimated_cost,
            "correlation_id": self.correlation_id,
        }


@dataclass
class ProviderPerformanceAggregate:
    """Robust aggregate over recent observations."""

    provider_id: str
    model_id: str
    sample_count: int = 0
    median_ttft_ms: Optional[float] = None
    p95_ttft_ms: Optional[float] = None
    median_generation_speed: Optional[float] = None
    failure_rate: float = 0.0
    timeout_rate: float = 0.0
    fallback_rate: float = 0.0
    freshness_seconds: Optional[float] = None
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "sample_count": self.sample_count,
            "median_ttft_ms": self.median_ttft_ms,
            "p95_ttft_ms": self.p95_ttft_ms,
            "median_generation_speed": self.median_generation_speed,
            "failure_rate": self.failure_rate,
            "timeout_rate": self.timeout_rate,
            "fallback_rate": self.fallback_rate,
            "freshness_seconds": self.freshness_seconds,
            "confidence": self.confidence,
        }


# Sensitivity of latency score to TTFT.  A 5-second TTFT scores ~0.37.
_LATENCY_SENSITIVITY_MS = 5000.0
# Speed normalization factor.  50 tokens/second is treated as excellent.
_SPEED_NORMALIZATION = 50.0
# Maximum observations retained per provider/model.
_DEFAULT_MAX_OBSERVATIONS = 100
# Maximum age of observations in seconds.
_DEFAULT_MAX_AGE_SECONDS = 3600.0
# Minimum samples before p95 is reported.
_P95_MIN_SAMPLES = 10
# Samples required for full confidence.
_CONFIDENCE_FULL_SAMPLES = 20


class ProviderPerformanceStore:
    """In-memory, bounded rolling store of provider performance observations."""

    def __init__(
        self,
        max_observations: int = _DEFAULT_MAX_OBSERVATIONS,
        max_age_seconds: float = _DEFAULT_MAX_AGE_SECONDS,
    ):
        self._max_observations = max(max_observations, 1)
        self._max_age_seconds = max(max_age_seconds, 0.001)
        self._observations: Dict[Tuple[str, str], deque] = defaultdict(deque)
        self._lock = RLock()

    def record(self, observation: ProviderPerformanceObservation) -> None:
        """Append an observation and enforce bounds."""
        with self._lock:
            key = (observation.provider_id, observation.model_id)
            dq = self._observations[key]
            dq.append(observation)
            self._prune(dq)

    def _prune(self, dq: deque) -> None:
        now = time.monotonic()
        while dq:
            too_old = (now - dq[0].timestamp) > self._max_age_seconds
            too_many = len(dq) > self._max_observations
            if not too_old and not too_many:
                break
            dq.popleft()

    def get_aggregate(
        self,
        provider_id: str,
        model_id: str,
        now: Optional[float] = None,
    ) -> ProviderPerformanceAggregate:
        """Return robust aggregate for a provider/model."""
        with self._lock:
            key = (provider_id, model_id)
            dq = self._observations.get(key, deque())
            self._prune(dq)
            obs = list(dq)
            return self._compute_aggregate(provider_id, model_id, obs, now or time.monotonic())

    @staticmethod
    def _compute_aggregate(
        provider_id: str,
        model_id: str,
        observations: List[ProviderPerformanceObservation],
        now: float,
    ) -> ProviderPerformanceAggregate:
        n = len(observations)
        if n == 0:
            return ProviderPerformanceAggregate(provider_id=provider_id, model_id=model_id)

        ttft = sorted(o.ttft_ms for o in observations if o.ttft_ms is not None)
        speeds = sorted(o.generation_tokens_per_second for o in observations if o.generation_tokens_per_second > 0)
        failures = sum(1 for o in observations if not o.success)
        timeouts = sum(1 for o in observations if o.timeout)
        fallbacks = sum(1 for o in observations if o.fallback_triggered)

        median_ttft = _median(ttft) if ttft else None
        p95_ttft = _percentile(ttft, 0.95) if len(ttft) >= _P95_MIN_SAMPLES else None
        median_speed = _median(speeds) if speeds else None

        newest = max(o.timestamp for o in observations)
        freshness = now - newest
        confidence = min(1.0, n / _CONFIDENCE_FULL_SAMPLES) * math.exp(-freshness / _DEFAULT_MAX_AGE_SECONDS)

        return ProviderPerformanceAggregate(
            provider_id=provider_id,
            model_id=model_id,
            sample_count=n,
            median_ttft_ms=median_ttft,
            p95_ttft_ms=p95_ttft,
            median_generation_speed=median_speed,
            failure_rate=failures / n,
            timeout_rate=timeouts / n,
            fallback_rate=fallbacks / n,
            freshness_seconds=freshness,
            confidence=round(confidence, 4),
        )

    def performance_score(
        self,
        provider_id: str,
        model_id: str,
        now: Optional[float] = None,
    ) -> float:
        """Normalized 0.0–1.0 soft score; 0.5 is neutral / no data."""
        agg = self.get_aggregate(provider_id, model_id, now)
        if agg.sample_count == 0:
            return 0.5

        # Latency: lower TTFT is better; use exponential decay
        if agg.median_ttft_ms is not None and agg.median_ttft_ms > 0:
            latency_fit = math.exp(-agg.median_ttft_ms / _LATENCY_SENSITIVITY_MS)
        else:
            latency_fit = 0.5

        # Throughput: higher generation speed is better, capped
        if agg.median_generation_speed is not None and agg.median_generation_speed > 0:
            throughput_fit = min(1.0, agg.median_generation_speed / _SPEED_NORMALIZATION)
        else:
            throughput_fit = 0.5

        # Reliability: fewer failures/timeouts are better
        reliability_fit = 1.0 - (agg.failure_rate * 0.7 + agg.timeout_rate * 0.3)

        # Freshness: prefer recent, well-sampled data
        freshness_confidence = agg.confidence

        # Documented formula
        return round(
            0.35 * latency_fit
            + 0.25 * throughput_fit
            + 0.30 * reliability_fit
            + 0.10 * freshness_confidence,
            4,
        )

    def provider_keys(self) -> List[Tuple[str, str]]:
        with self._lock:
            return list(self._observations.keys())

    def __len__(self) -> int:
        with self._lock:
            return sum(len(dq) for dq in self._observations.values())


def _median(values: List[float]) -> Optional[float]:
    if not values:
        return None
    n = len(values)
    mid = n // 2
    if n % 2:
        return values[mid]
    return (values[mid - 1] + values[mid]) / 2.0


def _percentile(values: List[float], p: float) -> float:
    if not values:
        raise ValueError("empty values")
    k = (len(values) - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return values[int(k)]
    d0 = values[int(f)] * (c - k)
    d1 = values[int(c)] * (k - f)
    return d0 + d1
