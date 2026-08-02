"""Model Ranking Engine.

Creates dynamic rankings based on quality, speed, cost,
reliability, and hardware compatibility.
Separates declared capabilities from observed capabilities.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from sentinel.core.event_bus import EventBus
from sentinel.core.performance_intelligence import ExecutionMetrics
from sentinel.core.event_types import MODEL_RANKING_UPDATED
from sentinel.core.events import SentinelEvent
from sentinel.core.feedback_engine import FeedbackEngine, FeedbackScore
from sentinel.core.performance_intelligence import PerformanceIntelligence

logger = logging.getLogger(__name__)


@dataclass
class ObservedCapabilities:
    supports_coding_score: float = 0.0
    supports_reasoning_score: float = 0.0
    supports_tool_calling_score: float = 0.0
    supports_vision_score: float = 0.0
    sample_count: int = 0


@dataclass
class ModelScore:
    model_id: str
    performance_score: float
    reliability_score: float
    average_latency: float
    average_cost: float
    total_executions: int
    feedback_positive_ratio: float
    feedback_count: int
    observed_capabilities: ObservedCapabilities = field(default_factory=ObservedCapabilities)
    rank: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "performance_score": self.performance_score,
            "reliability_score": self.reliability_score,
            "average_latency": self.average_latency,
            "average_cost": self.average_cost,
            "total_executions": self.total_executions,
            "feedback_positive_ratio": self.feedback_positive_ratio,
            "feedback_count": self.feedback_count,
            "observed_capabilities": {
                "supports_coding_score": self.observed_capabilities.supports_coding_score,
                "supports_reasoning_score": self.observed_capabilities.supports_reasoning_score,
                "supports_tool_calling_score": self.observed_capabilities.supports_tool_calling_score,
                "supports_vision_score": self.observed_capabilities.supports_vision_score,
                "sample_count": self.observed_capabilities.sample_count,
            },
            "rank": self.rank,
        }


class ModelRanking:
    def __init__(
        self,
        performance_intelligence: Optional[PerformanceIntelligence] = None,
        feedback_engine: Optional[FeedbackEngine] = None,
        event_bus: Optional[EventBus] = None,
        decay_factor: float = 0.95,
    ):
        self._perf = performance_intelligence
        self._feedback = feedback_engine
        self._event_bus = event_bus
        self._decay_factor = decay_factor
        self._scores: Dict[str, ModelScore] = {}
        self._audit_log: List[Dict[str, Any]] = []
        self._failure_penalties: Dict[str, float] = {}
        self._availability_scores: Dict[str, float] = {}
        self._recovery_times: Dict[str, float] = {}
        self._last_failure_at: Dict[str, float] = {}
        self._registry = None

    def set_model_registry(self, registry: Any) -> None:
        self._registry = registry

    @property
    def scores(self) -> Dict[str, ModelScore]:
        return dict(self._scores)

    # ── Failover / Reliability (FASE 4.7) ──────────────────────

    def apply_provider_failure(self, provider_id: str, model_ids: Optional[List[str]] = None) -> None:
        """Aplica una penalización de fallo a los modelos del proveedor."""
        import time
        now = time.time()
        self._last_failure_at[provider_id] = now
        models = model_ids or [provider_id]
        for mid in models:
            current = self._failure_penalties.get(mid, 0.0)
            self._failure_penalties[mid] = min(50.0, current + 15.0)
        self._audit_log.append({
            "action": "provider_failure",
            "provider": provider_id,
            "models": list(models),
            "timestamp": __import__("datetime").datetime.now().isoformat(),
        })

    def apply_provider_success(self, provider_id: str, model_ids: Optional[List[str]] = None) -> None:
        """Recupera gradualmente los modelos de un proveedor tras un éxito."""
        models = model_ids or [provider_id]
        for mid in models:
            current = self._failure_penalties.get(mid, 0.0)
            self._failure_penalties[mid] = max(0.0, current - 5.0)
        self._availability_scores.pop(provider_id, None)

    def set_availability_score(self, provider_id: str, score: float, recovery_seconds: float = 0.0) -> None:
        self._availability_scores[provider_id] = max(0.0, min(100.0, score))
        if recovery_seconds > 0:
            self._recovery_times[provider_id] = recovery_seconds

    def apply_circuit_breaker(self, cb: Any) -> None:
        """Sincroniza el estado del CircuitBreaker con el ranking."""
        try:
            for state in cb.get_all_states():
                provider_id = state["provider_id"]
                score = cb.availability_score(provider_id)
                self.set_availability_score(provider_id, score, cb.recovery_seconds(provider_id))
                if state["state"] == "open":
                    self.apply_provider_failure(provider_id)
        except Exception as e:
            logger.debug("apply_circuit_breaker failed: %s", e)

    def update_score(self, model_id: str, latency: float, success: bool, task_type: str) -> None:
        if self._perf is None:
            return
        self._perf.record_metric(
            ExecutionMetrics(
                model_id=model_id,
                task_type=task_type,
                intent="multi_model",
                latency=latency,
                tokens_used=0,
                cost=0.0,
                success=success,
            )
        )

    def compute_scores(self, model_ids: Optional[List[str]] = None) -> List[ModelScore]:
        if self._perf is None:
            return []
        summaries = self._perf.get_summary()
        if model_ids:
            summaries = [s for s in summaries if s.model_id in model_ids]

        result = []
        for summary in summaries:
            mid = summary.model_id

            reliability = summary.reliability_score

            if summary.total_executions > 0:
                latency_score = max(0, 100 - (summary.avg_latency / 10) * 100)
                latency_score = min(100, latency_score)
            else:
                latency_score = 50

            if summary.avg_cost > 0:
                cost_score = max(0, 100 - (summary.avg_cost / 0.01) * 100)
                cost_score = min(100, cost_score)
            else:
                cost_score = 100

            feedback_ratio = 0.5
            feedback_count = 0
            if self._feedback:
                fb_summaries = self._feedback.get_summary(model_id=mid)
                if fb_summaries:
                    fb_count = sum(s.total for s in fb_summaries)
                    pos_ratio = sum(s.positive for s in fb_summaries) / max(fb_count, 1)
                    feedback_ratio = pos_ratio
                    feedback_count = fb_count

            execution_score = min(100, (summary.total_executions / 10) * 100)

            availability = 100.0
            provider = self._provider_of(mid)
            if provider is not None:
                availability = self._availability_scores.get(provider, 100.0)
            failure_penalty = self._failure_penalties.get(mid, 0.0)
            availability_factor = availability / 100.0

            performance_score = (
                reliability * 0.35
                + latency_score * 0.20
                + cost_score * 0.15
                + feedback_ratio * 100 * 0.20
                + execution_score * 0.10
            )
            performance_score = performance_score * availability_factor - failure_penalty
            performance_score = round(performance_score, 1)

            observed = self._compute_observed_capabilities(mid)

            score = ModelScore(
                model_id=mid,
                performance_score=performance_score,
                reliability_score=reliability,
                average_latency=summary.avg_latency,
                average_cost=summary.avg_cost,
                total_executions=summary.total_executions,
                feedback_positive_ratio=round(feedback_ratio, 3),
                feedback_count=feedback_count,
                observed_capabilities=observed,
            )
            self._scores[mid] = score
            result.append(score)

        result.sort(key=lambda s: s.performance_score, reverse=True)
        for i, score in enumerate(result):
            score.rank = i + 1

        self._audit_log.append({
            "action": "rank_update",
            "timestamp": __import__("datetime").datetime.now().isoformat(),
            "ranked_models": len(result),
        })

        if self._event_bus:
            import asyncio
            try:
                asyncio.ensure_future(
                    self._event_bus.emit(
                        SentinelEvent.new(
                            event_type=MODEL_RANKING_UPDATED,
                            session_id="system",
                            request_id="",
                            component="model_ranking",
                            details={"ranked_models": len(result), "top_model": result[0].model_id if result else None},
                        )
                    )
                )
            except Exception:
                logger.warning("Failed to emit model ranking update event", exc_info=True)

        return result

    def _provider_of(self, model_id: str) -> Optional[str]:
        if self._registry is None:
            return None
        try:
            model = self._registry.get(model_id)
            return model.provider if model is not None else None
        except Exception:
            return None

    def _compute_observed_capabilities(self, model_id: str) -> ObservedCapabilities:
        if self._perf is None:
            return ObservedCapabilities()
        metrics = self._perf.get_metrics(model_id=model_id)
        if not metrics:
            return ObservedCapabilities()

        coding_success = 0
        coding_total = 0
        reasoning_success = 0
        reasoning_total = 0
        tool_success = 0
        tool_total = 0
        for m in metrics:
            tt = m.task_type.lower()
            if tt in ("coding", "code", "development"):
                coding_total += 1
                if m.success:
                    coding_success += 1
            if tt in ("reasoning", "analysis", "planning"):
                reasoning_total += 1
                if m.success:
                    reasoning_success += 1
            if tt in ("action", "tool", "automation", "tool_execution"):
                tool_total += 1
                if m.success:
                    tool_success += 1

        return ObservedCapabilities(
            supports_coding_score=round(coding_success / max(coding_total, 1) * 100, 1),
            supports_reasoning_score=round(reasoning_success / max(reasoning_total, 1) * 100, 1),
            supports_tool_calling_score=round(tool_success / max(tool_total, 1) * 100, 1),
            supports_vision_score=0.0,
            sample_count=len(metrics),
        )

    def get_top_k(self, k: int = 5, task_type: Optional[str] = None) -> List[ModelScore]:
        scores = list(self._scores.values())
        if task_type:
            scores = [s for s in scores if self._matches_task(s.model_id, task_type)]
        scores.sort(key=lambda s: s.performance_score, reverse=True)
        return scores[:k]

    def _matches_task(self, model_id: str, task_type: str) -> bool:
        if self._perf is None:
            return True
        metrics = self._perf.get_metrics(model_id=model_id)
        task_metrics = [m for m in metrics if m.task_type == task_type]
        return len(task_metrics) > 0

    def get_model_score(self, model_id: str) -> Optional[ModelScore]:
        return self._scores.get(model_id)

    def get_declared_vs_observed(self, model_id: str, declared_capabilities: Dict[str, bool]) -> Dict[str, Any]:
        score = self._scores.get(model_id)
        if score is None:
            return {"model_id": model_id, "observed": {}, "discrepancies": []}

        observed = score.observed_capabilities
        discrepancies = []
        for cap, declared in declared_capabilities.items():
            observed_score = getattr(observed, f"supports_{cap}_score", None)
            if observed_score is not None and declared and observed_score < 50:
                discrepancies.append({
                    "capability": cap,
                    "declared": declared,
                    "observed_score": observed_score,
                    "status": "underperforming",
                })
        return {
            "model_id": model_id,
            "declared": declared_capabilities,
            "observed": {
                "coding": observed.supports_coding_score,
                "reasoning": observed.supports_reasoning_score,
                "tool_calling": observed.supports_tool_calling_score,
                "vision": observed.supports_vision_score,
                "sample_count": observed.sample_count,
            },
            "discrepancies": discrepancies,
        }

    def get_audit_log(self) -> List[Dict[str, Any]]:
        return list(self._audit_log)
