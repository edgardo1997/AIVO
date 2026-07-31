"""FeedbackCycle — Ciclo de aprendizaje: Request → Selection → Execution → Feedback → Update Ranking.

Antes:
  Request → Model Selection → Execution → Result (fin)

Después:
  Request → Model Selection → Execution → Result → Feedback → Update Ranking → Future Decisions
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class FeedbackEntry:
    model_id: str
    task_type: str
    success: bool
    latency: float
    quality_score: float
    timestamp: str = ""
    user_id: str = ""
    session_id: str = ""
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelProfile:
    """Perfil de rendimiento aprendido para un modelo + tarea."""
    model_id: str
    task_type: str
    total_executions: int = 0
    successful_executions: int = 0
    total_latency: float = 0.0
    quality_sum: float = 0.0
    avg_quality: float = 0.5
    success_rate: float = 0.5
    avg_latency: float = 0.0
    last_used: str = ""
    score: float = 0.5

    def update(self, entry: FeedbackEntry) -> None:
        self.total_executions += 1
        if entry.success:
            self.successful_executions += 1
        self.total_latency += entry.latency
        self.quality_sum += entry.quality_score
        self.avg_latency = self.total_latency / self.total_executions
        self.avg_quality = self.quality_sum / self.total_executions
        self.success_rate = self.successful_executions / self.total_executions
        self.last_used = entry.timestamp or datetime.now(timezone.utc).isoformat()
        self.score = self.avg_quality * 0.5 + self.success_rate * 0.3 + max(0, 1 - self.avg_latency / 30) * 0.2

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "task_type": self.task_type,
            "total_executions": self.total_executions,
            "successful_executions": self.successful_executions,
            "success_rate": round(self.success_rate, 2),
            "avg_latency": round(self.avg_latency, 2),
            "avg_quality": round(self.avg_quality, 2),
            "score": round(self.score, 2),
            "last_used": self.last_used,
        }


class FeedbackCycle:
    """Ciclo completo de retroalimentación.

    Registra cada ejecución, mantiene perfiles por modelo+tarea,
    y expone datos para que RankingEngine mejore sus puntuaciones.
    """

    def __init__(self):
        self._profiles: Dict[str, ModelProfile] = {}
        self._history: List[FeedbackEntry] = []
        self._ranking_engine: Any = None

    def set_ranking_engine(self, engine: Any) -> None:
        self._ranking_engine = engine

    # ── Recording ─────────────────────────────────────────────

    def record_outcome(
        self,
        model_id: str,
        task_type: str,
        success: bool,
        latency: float,
        quality_score: float = 0.5,
        error: Optional[str] = None,
        user_id: str = "",
        session_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> FeedbackEntry:
        entry = FeedbackEntry(
            model_id=model_id,
            task_type=task_type,
            success=success,
            latency=latency,
            quality_score=quality_score,
            timestamp=datetime.now(timezone.utc).isoformat(),
            user_id=user_id,
            session_id=session_id,
            error=error,
            metadata=metadata or {},
        )
        self._history.append(entry)
        self._update_profile(entry)
        return entry

    def record_batch(self, entries: List[Dict[str, Any]]) -> List[FeedbackEntry]:
        results = []
        for e in entries:
            results.append(self.record_outcome(
                model_id=e["model_id"],
                task_type=e.get("task_type", ""),
                success=e.get("success", True),
                latency=e.get("latency", 0),
                quality_score=e.get("quality_score", 0.5),
                error=e.get("error"),
                user_id=e.get("user_id", ""),
                session_id=e.get("session_id", ""),
                metadata=e.get("metadata"),
            ))
        # Notificar al ranking engine después de batch
        self._notify_ranking()
        return results

    # ── Queries ───────────────────────────────────────────────

    def get_profile(self, model_id: str, task_type: str) -> Optional[ModelProfile]:
        key = self._profile_key(model_id, task_type)
        return self._profiles.get(key)

    def get_model_profiles(self, model_id: str) -> List[ModelProfile]:
        return [p for k, p in self._profiles.items() if k.startswith(f"{model_id}:")]

    def get_top_models(self, task_type: str, top_k: int = 5) -> List[ModelProfile]:
        profiles = [
            p for k, p in self._profiles.items() if k.endswith(f":{task_type}")
        ]
        profiles.sort(key=lambda p: p.score, reverse=True)
        return profiles[:top_k]

    def get_history(self, limit: int = 100) -> List[FeedbackEntry]:
        return self._history[-limit:]

    def clear(self) -> None:
        self._profiles.clear()
        self._history.clear()

    # ── Internal ──────────────────────────────────────────────

    def _update_profile(self, entry: FeedbackEntry) -> None:
        key = self._profile_key(entry.model_id, entry.task_type)
        if key not in self._profiles:
            self._profiles[key] = ModelProfile(
                model_id=entry.model_id,
                task_type=entry.task_type,
            )
        self._profiles[key].update(entry)

    def _notify_ranking(self) -> None:
        if self._ranking_engine and hasattr(self._ranking_engine, "update_scores_from_feedback"):
            try:
                self._ranking_engine.update_scores_from_feedback()
            except Exception as e:
                logger.warning("Ranking notification failed: %s", e)

    @staticmethod
    def _profile_key(model_id: str, task_type: str) -> str:
        return f"{model_id}:{task_type}"
