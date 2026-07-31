"""Performance Intelligence Engine.

Collects and analyzes execution metrics: response time, errors,
latency, resource consumption, cost, and perceived quality.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sentinel.core.event_bus import EventBus
from sentinel.core.event_types import (
    MODEL_EXECUTION_COMPLETED,
    MODEL_EXECUTION_FAILED,
    MODEL_EXECUTION_STARTED,
)
from sentinel.core.events import SentinelEvent

logger = logging.getLogger(__name__)


@dataclass
class ExecutionMetrics:
    model_id: str
    task_type: str
    intent: str
    latency: float
    tokens_used: int
    cost: float
    success: bool
    error: Optional[str] = None
    hardware_state: Optional[Dict[str, Any]] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "task_type": self.task_type,
            "intent": self.intent,
            "latency": self.latency,
            "tokens_used": self.tokens_used,
            "cost": self.cost,
            "success": self.success,
            "error": self.error,
            "hardware_state": self.hardware_state,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "timestamp": self.timestamp or datetime.now(timezone.utc).isoformat(),
        }


@dataclass
class ModelPerformanceSummary:
    model_id: str
    total_executions: int
    successful_executions: int
    failed_executions: int
    success_rate: float
    avg_latency: float
    max_latency: float
    min_latency: float
    avg_tokens_used: float
    avg_cost: float
    total_cost: float
    last_execution: Optional[str] = None
    recent_errors: List[str] = field(default_factory=list)

    @property
    def reliability_score(self) -> float:
        if self.total_executions == 0:
            return 0.0
        return round(self.success_rate * 100, 1)


class PerformanceIntelligence:
    def __init__(self, event_bus: Optional[EventBus] = None, max_history: int = 10000):
        self._event_bus = event_bus
        self._max_history = max_history
        self._metrics: List[ExecutionMetrics] = []
        self._subscribed = False

    @property
    def total_records(self) -> int:
        return len(self._metrics)

    def subscribe_to_events(self) -> None:
        if self._subscribed or self._event_bus is None:
            return
        self._event_bus.subscribe(MODEL_EXECUTION_STARTED, self._on_execution_started)
        self._event_bus.subscribe(MODEL_EXECUTION_COMPLETED, self._on_execution_completed)
        self._event_bus.subscribe(MODEL_EXECUTION_FAILED, self._on_execution_failed)
        self._subscribed = True
        logger.info("PerformanceIntelligence subscribed to execution events")

    def record_metric(self, metric: ExecutionMetrics) -> None:
        if not metric.timestamp:
            metric.timestamp = datetime.now(timezone.utc).isoformat()
        self._metrics.append(metric)
        if len(self._metrics) > self._max_history:
            self._metrics.pop(0)
        logger.debug(
            "Metric recorded: %s %s success=%s latency=%.2fs tokens=%d cost=%.6f",
            metric.model_id, metric.task_type, metric.success,
            metric.latency, metric.tokens_used, metric.cost,
        )

    def get_summary(self, model_id: Optional[str] = None) -> List[ModelPerformanceSummary]:
        filtered = self._metrics if model_id is None else [m for m in self._metrics if m.model_id == model_id]
        groups: Dict[str, List[ExecutionMetrics]] = defaultdict(list)
        for m in filtered:
            groups[m.model_id].append(m)

        result = []
        for mid, records in groups.items():
            successes = sum(1 for r in records if r.success)
            total = len(records)
            latencies = [r.latency for r in records]
            errors = [r.error for r in records if r.error]
            last_ts = max(r.timestamp for r in records) if records else None

            result.append(
                ModelPerformanceSummary(
                    model_id=mid,
                    total_executions=total,
                    successful_executions=successes,
                    failed_executions=total - successes,
                    success_rate=successes / total if total else 0.0,
                    avg_latency=sum(latencies) / len(latencies) if latencies else 0.0,
                    max_latency=max(latencies) if latencies else 0.0,
                    min_latency=min(latencies) if latencies else 0.0,
                    avg_tokens_used=sum(r.tokens_used for r in records) / total if total else 0.0,
                    avg_cost=sum(r.cost for r in records) / total if total else 0.0,
                    total_cost=sum(r.cost for r in records),
                    last_execution=last_ts,
                    recent_errors=errors[-10:],
                )
            )
        return result

    def get_model_summary(self, model_id: str) -> Optional[ModelPerformanceSummary]:
        summaries = self.get_summary(model_id=model_id)
        return summaries[0] if summaries else None

    def get_success_rate(self, model_id: str) -> float:
        summary = self.get_model_summary(model_id)
        return summary.success_rate if summary else 0.0

    def get_avg_latency(self, model_id: str) -> float:
        summary = self.get_model_summary(model_id)
        return summary.avg_latency if summary else 0.0

    def get_metrics(self, model_id: Optional[str] = None) -> List[ExecutionMetrics]:
        if model_id:
            return [m for m in self._metrics if m.model_id == model_id]
        return list(self._metrics)

    def get_metrics_by_task(self, task_type: str) -> List[ExecutionMetrics]:
        return [m for m in self._metrics if m.task_type == task_type]

    def clear(self) -> None:
        self._metrics.clear()

    async def _on_execution_started(self, event: SentinelEvent) -> None:
        logger.debug("Execution started: %s", event.event_id)

    async def _on_execution_completed(self, event: SentinelEvent) -> None:
        details = event.details or {}
        self.record_metric(
            ExecutionMetrics(
                model_id=details.get("model_id", "unknown"),
                task_type=details.get("task_type", "unknown"),
                intent=details.get("intent", "unknown"),
                latency=details.get("latency", 0.0),
                tokens_used=details.get("tokens_used", 0),
                cost=details.get("cost", 0.0),
                success=True,
                error=None,
                hardware_state=details.get("hardware_state"),
                prompt_tokens=details.get("prompt_tokens", 0),
                completion_tokens=details.get("completion_tokens", 0),
            )
        )

    async def _on_execution_failed(self, event: SentinelEvent) -> None:
        details = event.details or {}
        self.record_metric(
            ExecutionMetrics(
                model_id=details.get("model_id", "unknown"),
                task_type=details.get("task_type", "unknown"),
                intent=details.get("intent", "unknown"),
                latency=details.get("latency", 0.0),
                tokens_used=details.get("tokens_used", 0),
                cost=details.get("cost", 0.0),
                success=False,
                error=details.get("error", "unknown error"),
                hardware_state=details.get("hardware_state"),
                prompt_tokens=details.get("prompt_tokens", 0),
                completion_tokens=details.get("completion_tokens", 0),
            )
        )
