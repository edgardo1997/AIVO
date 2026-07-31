"""TaskTimePredictor — Predice duración de tareas basado en historial.

Entrada: TaskProfile (tipo de tarea, modelo, complejidad, historial)
Salida:  {estimated_seconds, confidence, min_estimate, max_estimate}

Ejemplo:
  "analiza 500 archivos" → {estimated: 35s, confidence: 0.82, min: 32, max: 40}
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from math import sqrt
from statistics import mean, stdev
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class TimePrediction:
    estimated_seconds: float
    confidence: float
    min_estimate: float
    max_estimate: float
    sample_count: int
    task_type: str
    model_id: str = ""
    complexity_factor: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "estimated_seconds": round(self.estimated_seconds, 1),
            "estimated_display": self._display(),
            "confidence": round(self.confidence, 2),
            "min_estimate": round(self.min_estimate, 1),
            "max_estimate": round(self.max_estimate, 1),
            "sample_count": self.sample_count,
            "task_type": self.task_type,
            "model_id": self.model_id,
        }

    def _display(self) -> str:
        if self.estimated_seconds < 60:
            return f"{self.estimated_seconds:.0f}s"
        return f"{self.estimated_seconds / 60:.1f}min"


@dataclass
class TaskProfile:
    """Perfil de una tarea para predicción."""
    task_type: str
    model_id: str = ""
    complexity: float = 1.0
    estimated_input_tokens: int = 0
    estimated_output_tokens: int = 0
    file_count: int = 0
    file_size_mb: float = 0.0


# Baseline latencies by task type (seconds, when no history exists)
TASK_BASELINES: Dict[str, float] = {
    "chat": 1.5,
    "tool": 3.0,
    "code": 8.0,
    "reasoning": 5.0,
    "analysis": 6.0,
    "search": 2.0,
    "vision": 4.0,
    "embedding": 0.5,
}


class TaskTimePredictor:
    """Predice tiempo de ejecución basado en datos históricos.

    Se integra con PerformanceIntelligence para obtener métricas
    históricas y FeedbackCycle para perfiles de ejecución.
    """

    def __init__(
        self,
        performance_intelligence: Any = None,
        feedback_cycle: Any = None,
    ):
        self._perf = performance_intelligence
        self._feedback = feedback_cycle
        self._history: Dict[str, List[float]] = {}
        self._predictions_made: int = 0

    def set_performance_intelligence(self, perf: Any) -> None:
        self._perf = perf

    def set_feedback_cycle(self, feedback: Any) -> None:
        self._feedback = feedback

    @property
    def predictions_count(self) -> int:
        return self._predictions_made

    def predict(self, profile: TaskProfile) -> TimePrediction:
        """Predice el tiempo para un perfil de tarea."""
        key = self._key(profile.task_type, profile.model_id)
        samples = self._get_samples(key, profile)
        complexity = profile.complexity

        if len(samples) >= 3:
            avg = mean(samples) * complexity
            std = stdev(samples) if len(samples) > 1 else avg * 0.2
            sample_count = len(samples)
            confidence = min(0.95, 0.5 + (sample_count / 100) * 0.45)
        elif len(samples) >= 1:
            avg = mean(samples) * complexity
            std = avg * 0.3
            sample_count = len(samples)
            confidence = 0.5
        else:
            baseline = TASK_BASELINES.get(profile.task_type, 3.0) * complexity
            if profile.estimated_input_tokens > 0:
                baseline += profile.estimated_input_tokens / 1000 * 1.5
            if profile.file_count > 0:
                baseline += profile.file_count * 0.5
            if profile.file_size_mb > 10:
                baseline += profile.file_size_mb / 10 * 0.3
            avg = baseline
            std = baseline * 0.4
            sample_count = 0
            confidence = 0.3

        self._predictions_made += 1
        return TimePrediction(
            estimated_seconds=avg,
            confidence=confidence,
            min_estimate=max(0.1, avg - 2 * std),
            max_estimate=avg + 2 * std,
            sample_count=sample_count,
            task_type=profile.task_type,
            model_id=profile.model_id,
            complexity_factor=complexity,
        )

    def record_actual(self, task_type: str, model_id: str, actual_seconds: float) -> None:
        """Registra el tiempo real para mejorar predicciones futuras."""
        key = self._key(task_type, model_id)
        if key not in self._history:
            self._history[key] = []
        self._history[key].append(actual_seconds)
        # Keep last 100 samples per key
        if len(self._history[key]) > 100:
            self._history[key] = self._history[key][-100:]

    def get_statistics(self, task_type: str, model_id: str = "") -> Dict[str, Any]:
        """Estadísticas de predicción para un tipo de tarea."""
        key = self._key(task_type, model_id)
        samples = self._history.get(key, [])
        if not samples:
            return {"samples": 0}
        return {
            "samples": len(samples),
            "mean": round(mean(samples), 2),
            "min": round(min(samples), 2),
            "max": round(max(samples), 2),
            "stdev": round(stdev(samples), 2) if len(samples) > 1 else 0,
        }

    def clear(self) -> None:
        self._history.clear()

    def _get_samples(self, key: str, profile: TaskProfile) -> List[float]:
        samples = list(self._history.get(key, []))
        if self._perf and hasattr(self._perf, "get_model_metrics"):
            try:
                metrics = self._perf.get_model_metrics(profile.model_id, profile.task_type)
                if metrics and "avg_latency_ms" in metrics:
                    samples.append(metrics["avg_latency_ms"] / 1000)
            except Exception:
                pass
        if self._feedback:
            prof = self._feedback.get_profile(profile.model_id, profile.task_type)
            if prof and prof.avg_latency > 0:
                samples.append(prof.avg_latency)
        return samples

    @staticmethod
    def _key(task_type: str, model_id: str) -> str:
        return f"{model_id}:{task_type}" if model_id else task_type
