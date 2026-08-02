"""RankingEngine — Puntuación dinámica de modelos.

Fórmula de puntuación:
  score = quality * 0.35 + success_rate * 0.25 + speed * 0.20
          + cost_efficiency * 0.10 + resource_efficiency * 0.10

Antes: selección por nombre fijo.
Después: selección por puntuación dinámica según tarea + experiencia.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sentinel.intelligence.model_registry import ModelRegistry

logger = logging.getLogger(__name__)


@dataclass
class RankedModel:
    model_id: str
    provider: str
    score: float
    quality_score: float
    success_rate: float
    speed_score: float
    cost_score: float
    resource_score: float
    total_executions: int
    average_latency: float
    task_type: str
    rank: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "provider": self.provider,
            "score": round(self.score, 2),
            "quality_score": round(self.quality_score, 2),
            "success_rate": round(self.success_rate, 2),
            "speed_score": round(self.speed_score, 2),
            "cost_score": round(self.cost_score, 2),
            "resource_score": round(self.resource_score, 2),
            "total_executions": self.total_executions,
            "average_latency": round(self.average_latency, 2),
            "task_type": self.task_type,
            "rank": self.rank,
        }


class RankingEngine:
    """Motor de ranking dinámico.

    Puntúa modelos en tiempo real combinando:
      - Calidad observada (feedback)
      - Tasa de éxito histórica
      - Velocidad (latencia promedio)
      - Eficiencia de costo
      - Eficiencia de recursos

    Se integra con ModelRegistry para conocer modelos disponibles
    y con PerformanceIntelligence + FeedbackEngine para datos históricos.
    """

    def __init__(
        self,
        model_registry: Optional[ModelRegistry] = None,
        performance_intelligence: Any = None,
        feedback_engine: Any = None,
    ):
        self._registry = model_registry
        self._perf = performance_intelligence
        self._feedback = feedback_engine
        self._history: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._scores: Dict[str, RankedModel] = {}

    # ── Setters ───────────────────────────────────────────────

    def set_registry(self, registry: ModelRegistry) -> None:
        self._registry = registry

    def set_performance_intelligence(self, perf: Any) -> None:
        self._perf = perf

    def set_feedback_engine(self, feedback: Any) -> None:
        self._feedback = feedback

    # ── Scoring API ────────────────────────────────────────────

    def rank_for_task(self, task_type: str, top_k: int = 5) -> List[RankedModel]:
        """Rankea modelos para una tarea específica."""
        models = self._get_candidates(task_type)
        ranked = []
        for m in models:
            stats = self._get_model_stats(m["id"], m.get("provider", ""), task_type)
            score, components = self._compute_score(stats)
            ranked.append(RankedModel(
                model_id=m["id"],
                provider=m.get("provider", "unknown"),
                score=score,
                **components,
                total_executions=stats.get("executions", 0),
                average_latency=stats.get("avg_latency", 0),
                task_type=task_type,
            ))
        ranked.sort(key=lambda x: x.score, reverse=True)
        for i, r in enumerate(ranked):
            r.rank = i + 1
        self._scores = {r.model_id: r for r in ranked}
        return ranked[:top_k]

    def get_top_k(self, task_type: str, k: int = 3) -> List[RankedModel]:
        return self.rank_for_task(task_type, top_k=k)

    def get_model_score(self, model_id: str) -> Optional[RankedModel]:
        return self._scores.get(model_id)

    def update_score(self, model_id: str, latency: float, success: bool, task_type: str) -> None:
        """Actualiza puntuación tras una ejecución."""
        key = f"{model_id}:{task_type}"
        self._history[key].append({
            "latency": latency,
            "success": success,
            "task_type": task_type,
        })
        # Recompute score for this model
        models = self._get_candidates(task_type)
        for m in models:
            if m["id"] == model_id:
                stats = self._get_model_stats(model_id, m.get("provider", ""), task_type)
                score, components = self._compute_score(stats)
                self._scores[model_id] = RankedModel(
                    model_id=model_id,
                    provider=m.get("provider", "unknown"),
                    score=score,
                    **components,
                    total_executions=stats.get("executions", 0),
                    average_latency=stats.get("avg_latency", 0),
                    task_type=task_type,
                )
                break

    # ── Internal ──────────────────────────────────────────────

    def _get_candidates(self, task_type: str) -> List[Dict[str, Any]]:
        if self._registry:
            models = self._registry.available_models()
            return [
                {"id": m.name, "provider": m.provider, "capabilities": m.capabilities, "cost": m.cost}
                for m in models
            ]
        return []

    def _get_model_stats(self, model_id: str, provider: str, task_type: str) -> Dict[str, Any]:
        stats: Dict[str, Any] = {
            "executions": 0, "success_count": 0, "avg_latency": 0,
            "total_latency": 0, "quality": 0.5,
        }
        key = f"{model_id}:{task_type}"
        history = self._history.get(key, [])
        if history:
            stats["executions"] = len(history)
            stats["success_count"] = sum(1 for h in history if h["success"])
            stats["total_latency"] = sum(h["latency"] for h in history)
            stats["avg_latency"] = stats["total_latency"] / len(history) if history else 0
        if self._perf and hasattr(self._perf, "get_model_metrics"):
            try:
                metrics = self._perf.get_model_metrics(model_id, task_type)
                if metrics:
                    stats["executions"] = max(stats["executions"], metrics.get("total", 0))
                    stats["avg_latency"] = stats["avg_latency"] or metrics.get("avg_latency_ms", 0) / 1000
                    stats["quality"] = metrics.get("quality_score", 0.5)
            except Exception:
                logger.warning("Failed to load metrics for model '%s'", model_id, exc_info=True)
        return stats

    def _compute_score(self, stats: Dict[str, Any]) -> tuple:
        executions = stats.get("executions", 0)
        successes = stats.get("success_count", 0)
        success_rate = successes / executions if executions > 0 else 0.5
        avg_latency = stats.get("avg_latency", 1.0) or 0.001
        quality = stats.get("quality", 0.5)
        speed = max(0, 1.0 - (avg_latency / 30.0)) if avg_latency > 0 else 0.5
        cost_eff = 0.5
        resource_eff = 0.5

        score = (
            quality * 0.35 + success_rate * 0.25 + speed * 0.20
            + cost_eff * 0.10 + resource_eff * 0.10
        )

        components = {
            "quality_score": quality,
            "success_rate": success_rate,
            "speed_score": speed,
            "cost_score": cost_eff,
            "resource_score": resource_eff,
        }
        return score, components
