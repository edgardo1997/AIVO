"""Normalized routing and inference metrics."""

from __future__ import annotations

import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class RoutingMetric:
    request_id: str
    correlation_id: str
    provider: str
    model: str
    operation: str
    routing_reason: str
    candidate_count: int
    latency_ms: float
    time_to_first_token_ms: Optional[float]
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost: float
    reserved_cost: float
    actual_cost: float
    fallback_used: bool
    fallback_reason: str
    status: str
    error_code: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class MetricsStore:
    """In-memory normalized metrics store with privacy guardrails."""

    FORBIDDEN_KEYS = {"prompt", "response", "messages", "headers", "api_key", "secret", "document"}

    def __init__(self):
        self._records: List[RoutingMetric] = []
        self._lock = threading.Lock()

    def record(self, metric: RoutingMetric) -> None:
        for key in self.FORBIDDEN_KEYS:
            if key in asdict(metric).values():
                raise ValueError(f"Metric cannot contain {key}")
        with self._lock:
            self._records.append(metric)

    def query(self, correlation_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            records = list(self._records)
        if correlation_id:
            records = [r for r in records if r.correlation_id == correlation_id]
        return [asdict(r) for r in records]

    def clear(self) -> None:
        with self._lock:
            self._records.clear()
