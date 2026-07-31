"""FeedbackRepository — Persistir resultados de tareas.

Guarda: éxito/error, satisfacción, modelo usado, tiempo empleado.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sentinel.storage.database import StorageEngine
from sentinel.storage.models import FeedbackRecord

logger = logging.getLogger(__name__)


class FeedbackRepository:
    def __init__(self, engine: StorageEngine):
        self._engine = engine

    async def save(self, record: FeedbackRecord) -> None:
        row = record.to_row()
        await self._engine.execute(
            """INSERT INTO feedback_records
               (id, model_id, task_type, success, quality_score, latency, error, user_id, session_id, metadata, created_at)
               VALUES (:id, :model_id, :task_type, :success, :quality_score, :latency, :error, :user_id, :session_id, :metadata, :created_at)""",
            row,
        )

    async def save_batch(self, records: List[FeedbackRecord]) -> None:
        for r in records:
            await self.save(r)

    async def list_all(self, limit: int = 20000) -> List[FeedbackRecord]:
        rows = await self._engine.execute(
            "SELECT * FROM feedback_records ORDER BY created_at DESC LIMIT :lim",
            {"lim": limit},
        )
        return [FeedbackRecord.from_row(dict(r)) for r in rows]

    async def list_by_model(self, model_id: str, limit: int = 100) -> List[FeedbackRecord]:
        rows = await self._engine.execute(
            "SELECT * FROM feedback_records WHERE model_id = :mid ORDER BY created_at DESC LIMIT :lim",
            {"mid": model_id, "lim": limit},
        )
        return [FeedbackRecord.from_row(dict(r)) for r in rows]

    async def list_by_task(self, task_type: str, limit: int = 100) -> List[FeedbackRecord]:
        rows = await self._engine.execute(
            "SELECT * FROM feedback_records WHERE task_type = :tt ORDER BY created_at DESC LIMIT :lim",
            {"tt": task_type, "lim": limit},
        )
        return [FeedbackRecord.from_row(dict(r)) for r in rows]

    async def get_model_summary(self, model_id: str) -> Dict[str, Any]:
        rows = await self._engine.execute(
            """SELECT COUNT(*) as total, SUM(success) as successes, AVG(quality_score) as avg_quality,
                      AVG(latency) as avg_latency
               FROM feedback_records WHERE model_id = :mid""",
            {"mid": model_id},
        )
        if not rows:
            return {"model_id": model_id, "total": 0}
        r = rows[0]
        total = r["total"] or 0
        return {
            "model_id": model_id,
            "total": total,
            "successes": r["successes"] or 0,
            "success_rate": round((r["successes"] or 0) / total, 2) if total > 0 else 0,
            "avg_quality": round(r["avg_quality"] or 0, 2),
            "avg_latency": round(r["avg_latency"] or 0, 2),
        }

    async def get_task_summary(self, task_type: str) -> Dict[str, Any]:
        rows = await self._engine.execute(
            """SELECT COUNT(*) as total, SUM(success) as successes, AVG(latency) as avg_latency
               FROM feedback_records WHERE task_type = :tt""",
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
            "success_rate": round((r["successes"] or 0) / total, 2) if total > 0 else 0,
            "avg_latency": round(r["avg_latency"] or 0, 2),
        }

    async def delete_older_than(self, days: int) -> int:
        from datetime import datetime, timedelta, timezone
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        await self._engine.execute(
            "DELETE FROM feedback_records WHERE created_at < :cutoff",
            {"cutoff": cutoff},
        )
        return 0

    async def count(self) -> int:
        rows = await self._engine.execute("SELECT COUNT(*) as cnt FROM feedback_records")
        return rows[0]["cnt"] if rows else 0
