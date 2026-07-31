"""IntelligenceStorage — Persistencia de datos de inteligencia.

Guarda/recupera:
  - historial de modelos
  - métricas de rendimiento
  - predicciones
  - resultados de feedback

Tabla propuesta: model_metrics
  id, model_name, task_type, latency, success, quality_score, resource_usage, created_at
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class MetricRecord:
    id: str = ""
    model_name: str = ""
    task_type: str = ""
    latency: float = 0.0
    success: bool = True
    quality_score: float = 0.5
    resource_usage: float = 0.0
    tokens_used: int = 0
    cost: float = 0.0
    created_at: str = ""


class IntelligenceStorage:
    """Persistencia para datos de la capa de inteligencia.

    Almacena en memoria con opción de exportación/importación.
    En producción, reemplazar por SQLite/PostgreSQL.
    """

    def __init__(self):
        self._metrics: List[MetricRecord] = []
        self._predictions: List[Dict[str, Any]] = []
        self._feedback: List[Dict[str, Any]] = []

    # ── Metrics ───────────────────────────────────────────────

    def save_metric(self, record: MetricRecord) -> None:
        if not record.id:
            record.id = f"m_{datetime.now(timezone.utc).timestamp()}"
        if not record.created_at:
            record.created_at = datetime.now(timezone.utc).isoformat()
        self._metrics.append(record)

    def save_metrics_batch(self, records: List[MetricRecord]) -> None:
        for r in records:
            self.save_metric(r)

    def get_metrics(
        self,
        model_name: Optional[str] = None,
        task_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[MetricRecord]:
        results = list(self._metrics)
        if model_name:
            results = [r for r in results if r.model_name == model_name]
        if task_type:
            results = [r for r in results if r.task_type == task_type]
        return results[-limit:]

    def get_model_summary(self, model_name: str) -> Dict[str, Any]:
        """Resumen de métricas para un modelo."""
        metrics = [m for m in self._metrics if m.model_name == model_name]
        if not metrics:
            return {"model_name": model_name, "total": 0}
        successes = sum(1 for m in metrics if m.success)
        total_latency = sum(m.latency for m in metrics)
        return {
            "model_name": model_name,
            "total": len(metrics),
            "success_count": successes,
            "success_rate": round(successes / len(metrics), 2) if metrics else 0,
            "avg_latency": round(total_latency / len(metrics), 2) if metrics else 0,
            "avg_quality": round(sum(m.quality_score for m in metrics) / len(metrics), 2) if metrics else 0,
        }

    def get_all_summaries(self) -> List[Dict[str, Any]]:
        """Resumen de todos los modelos."""
        models = set(m.model_name for m in self._metrics)
        return [self.get_model_summary(m) for m in sorted(models)]

    # ── Predictions ───────────────────────────────────────────

    def save_prediction(self, prediction: Dict[str, Any]) -> None:
        entry = dict(prediction)
        entry["stored_at"] = datetime.now(timezone.utc).isoformat()
        self._predictions.append(entry)

    def get_predictions(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._predictions[-limit:]

    # ── Feedback ──────────────────────────────────────────────

    def save_feedback(self, entry: Dict[str, Any]) -> None:
        self._feedback.append(entry)

    def get_feedback(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._feedback[-limit:]

    # ── Import/Export ─────────────────────────────────────────

    def export_all(self) -> Dict[str, Any]:
        return {
            "metrics": [asdict(m) for m in self._metrics],
            "predictions": self._predictions,
            "feedback": self._feedback,
            "exported_at": datetime.now(timezone.utc).isoformat(),
        }

    def import_all(self, data: Dict[str, Any]) -> int:
        count = 0
        for m in data.get("metrics", []):
            self._metrics.append(MetricRecord(**m))
            count += 1
        self._predictions.extend(data.get("predictions", []))
        self._feedback.extend(data.get("feedback", []))
        return count

    def clear(self) -> None:
        self._metrics.clear()
        self._predictions.clear()
        self._feedback.clear()

    @property
    def metric_count(self) -> int:
        return len(self._metrics)
