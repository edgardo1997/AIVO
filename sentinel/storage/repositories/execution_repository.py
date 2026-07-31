"""ExecutionRepository — Persistir historial de ejecuciones.

Guarda: execution_id, timestamp, user_request, intent, task_type,
selected_model, tools_used, duration, success, failure_reason, risk_level,
cost, confidence_score.
Permite recuperar experiencia después de reinicio (FASE 5.4).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sentinel.storage.database import StorageEngine
from sentinel.storage.models import StoredExecution

logger = logging.getLogger(__name__)


class ExecutionRepository:
    def __init__(self, engine: StorageEngine):
        self._engine = engine

    async def save(self, record: StoredExecution) -> None:
        row = record.to_row()
        await self._engine.execute(
            """INSERT OR REPLACE INTO executions
               (execution_id, timestamp, user_request, intent, task_type,
                selected_model, tools_used, duration, success, failure_reason,
                risk_level, cost, confidence_score, error)
               VALUES (:execution_id, :timestamp, :user_request, :intent, :task_type,
                       :selected_model, :tools_used, :duration, :success, :failure_reason,
                       :risk_level, :cost, :confidence_score, :error)""",
            row,
        )

    async def save_batch(self, records: List[StoredExecution]) -> None:
        for r in records:
            await self.save(r)

    async def get(self, execution_id: str) -> Optional[StoredExecution]:
        rows = await self._engine.execute(
            "SELECT * FROM executions WHERE execution_id = :eid",
            {"eid": execution_id},
        )
        if rows:
            return StoredExecution.from_row(dict(rows[0]))
        return None

    async def list_recent(self, limit: int = 50) -> List[StoredExecution]:
        rows = await self._engine.execute(
            "SELECT * FROM executions ORDER BY timestamp DESC LIMIT :lim",
            {"lim": limit},
        )
        return [StoredExecution.from_row(dict(r)) for r in rows]

    async def list_by_model(self, model_id: str, limit: int = 50) -> List[StoredExecution]:
        rows = await self._engine.execute(
            "SELECT * FROM executions WHERE selected_model = :mid ORDER BY timestamp DESC LIMIT :lim",
            {"mid": model_id, "lim": limit},
        )
        return [StoredExecution.from_row(dict(r)) for r in rows]

    async def list_by_task(self, task_type: str, limit: int = 50) -> List[StoredExecution]:
        rows = await self._engine.execute(
            "SELECT * FROM executions WHERE task_type = :tt ORDER BY timestamp DESC LIMIT :lim",
            {"tt": task_type, "lim": limit},
        )
        return [StoredExecution.from_row(dict(r)) for r in rows]

    async def list_since(self, timestamp: str, limit: int = 500) -> List[StoredExecution]:
        rows = await self._engine.execute(
            "SELECT * FROM executions WHERE timestamp >= :ts ORDER BY timestamp DESC LIMIT :lim",
            {"ts": timestamp, "lim": limit},
        )
        return [StoredExecution.from_row(dict(r)) for r in rows]

    async def delete_older_than(self, days: int) -> int:
        from datetime import datetime, timedelta, timezone
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        await self._engine.execute(
            "DELETE FROM executions WHERE timestamp < :cutoff",
            {"cutoff": cutoff},
        )
        return 0

    async def count(self) -> int:
        rows = await self._engine.execute("SELECT COUNT(*) as cnt FROM executions")
        return rows[0]["cnt"] if rows else 0

    async def get_last_update(self) -> Optional[str]:
        rows = await self._engine.execute(
            "SELECT MAX(timestamp) as last_ts FROM executions"
        )
        if rows:
            return rows[0]["last_ts"]
        return None
