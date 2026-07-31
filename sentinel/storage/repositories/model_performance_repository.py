"""ModelPerformanceRepository — Memoria de rendimiento de modelos.

Guarda eventos de rendimiento por modelo/tarea y agrega:
success_rate, average_latency, average_cost, failure_count, last_used, confidence.
Alimenta ModelRanking tras reinicio (FASE 5.5).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sentinel.storage.database import StorageEngine
from sentinel.storage.models import ModelPerformanceEvent

logger = logging.getLogger(__name__)


class ModelPerformanceRepository:
    def __init__(self, engine: StorageEngine):
        self._engine = engine

    async def save(self, event: ModelPerformanceEvent) -> None:
        row = event.to_row()
        await self._engine.execute(
            """INSERT INTO model_performance
               (model_name, task_type, latency, success, quality_score,
                resource_usage, tokens_used, cost, created_at)
               VALUES (:model_name, :task_type, :latency, :success, :quality_score,
                       :resource_usage, :tokens_used, :cost, :created_at)""",
            row,
        )

    async def save_batch(self, events: List[ModelPerformanceEvent]) -> None:
        for e in events:
            await self.save(e)

    async def list_all(self, limit: int = 10000) -> List[ModelPerformanceEvent]:
        rows = await self._engine.execute(
            "SELECT * FROM model_performance ORDER BY created_at DESC LIMIT :lim",
            {"lim": limit},
        )
        return [ModelPerformanceEvent.from_row(dict(r)) for r in rows]

    async def list_by_model(self, model_name: str, limit: int = 1000) -> List[ModelPerformanceEvent]:
        rows = await self._engine.execute(
            "SELECT * FROM model_performance WHERE model_name = :mn ORDER BY created_at DESC LIMIT :lim",
            {"mn": model_name, "lim": limit},
        )
        return [ModelPerformanceEvent.from_row(dict(r)) for r in rows]

    async def get_model_summary(self, model_name: str, task_type: Optional[str] = None) -> Dict[str, Any]:
        if task_type:
            rows = await self._engine.execute(
                """SELECT COUNT(*) as total, SUM(success) as successes, AVG(latency) as avg_latency,
                          AVG(cost) as avg_cost, MAX(created_at) as last_used
                   FROM model_performance WHERE model_name = :mn AND task_type = :tt""",
                {"mn": model_name, "tt": task_type},
            )
        else:
            rows = await self._engine.execute(
                """SELECT COUNT(*) as total, SUM(success) as successes, AVG(latency) as avg_latency,
                          AVG(cost) as avg_cost, MAX(created_at) as last_used
                   FROM model_performance WHERE model_name = :mn""",
                {"mn": model_name},
            )
        if not rows:
            return {"model_name": model_name, "total": 0}
        r = rows[0]
        total = r["total"] or 0
        failures = (r["successes"] or 0) if total else 0
        failure_count = total - failures
        success_rate = round((r["successes"] or 0) / total, 3) if total > 0 else 0.0
        confidence = min(1.0, total / 100.0)
        return {
            "model_name": model_name,
            "task_type": task_type,
            "total": total,
            "success_rate": success_rate,
            "average_latency": round(r["avg_latency"] or 0, 3),
            "average_cost": round(r["avg_cost"] or 0, 5),
            "failure_count": failure_count,
            "last_used": r["last_used"],
            "confidence": round(confidence, 3),
        }

    async def get_task_summary(self, task_type: str) -> Dict[str, Any]:
        rows = await self._engine.execute(
            """SELECT COUNT(*) as total, SUM(success) as successes, AVG(latency) as avg_latency
               FROM model_performance WHERE task_type = :tt""",
            {"tt": task_type},
        )
        if not rows:
            return {"task_type": task_type, "total": 0}
        r = rows[0]
        total = r["total"] or 0
        return {
            "task_type": task_type,
            "total": total,
            "successes": r["successes"] or 0,
            "success_rate": round((r["successes"] or 0) / total, 3) if total > 0 else 0,
            "avg_latency": round(r["avg_latency"] or 0, 3),
        }

    async def delete_older_than(self, days: int) -> int:
        from datetime import datetime, timedelta, timezone
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        await self._engine.execute(
            "DELETE FROM model_performance WHERE created_at < :cutoff",
            {"cutoff": cutoff},
        )
        return 0

    async def count(self) -> int:
        rows = await self._engine.execute("SELECT COUNT(*) as cnt FROM model_performance")
        return rows[0]["cnt"] if rows else 0

    async def get_last_update(self) -> Optional[str]:
        rows = await self._engine.execute(
            "SELECT MAX(created_at) as last_ts FROM model_performance"
        )
        if rows:
            return rows[0]["last_ts"]
        return None
