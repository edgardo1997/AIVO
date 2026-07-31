"""DecisionRepository — Persistir historial de decisiones.

Guarda: qué decidió Sentinel, por qué, qué modelo eligió, nivel de riesgo.
Para auditoría y análisis histórico.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sentinel.storage.database import StorageEngine
from sentinel.storage.models import DecisionRecord

logger = logging.getLogger(__name__)


class DecisionRepository:
    def __init__(self, engine: StorageEngine):
        self._engine = engine

    async def save(self, record: DecisionRecord) -> None:
        row = record.to_row()
        await self._engine.execute(
            """INSERT INTO decision_history
               (id, request, intent, decision, risk_level, selected_model, reason, execution_id, created_at)
               VALUES (:id, :request, :intent, :decision, :risk_level, :selected_model, :reason, :execution_id, :created_at)""",
            row,
        )

    async def save_batch(self, records: List[DecisionRecord]) -> None:
        for r in records:
            await self.save(r)

    async def list_recent(self, limit: int = 50) -> List[DecisionRecord]:
        rows = await self._engine.execute(
            "SELECT * FROM decision_history ORDER BY created_at DESC LIMIT :lim",
            {"lim": limit},
        )
        return [DecisionRecord.from_row(dict(r)) for r in rows]

    async def list_by_model(self, model_id: str, limit: int = 50) -> List[DecisionRecord]:
        rows = await self._engine.execute(
            "SELECT * FROM decision_history WHERE selected_model = :mid ORDER BY created_at DESC LIMIT :lim",
            {"mid": model_id, "lim": limit},
        )
        return [DecisionRecord.from_row(dict(r)) for r in rows]

    async def list_by_decision(self, decision: str, limit: int = 50) -> List[DecisionRecord]:
        rows = await self._engine.execute(
            "SELECT * FROM decision_history WHERE decision = :dec ORDER BY created_at DESC LIMIT :lim",
            {"dec": decision, "lim": limit},
        )
        return [DecisionRecord.from_row(dict(r)) for r in rows]

    async def get_model_decision_summary(self, model_id: str) -> Dict[str, Any]:
        rows = await self._engine.execute(
            """SELECT COUNT(*) as total,
                      SUM(CASE WHEN decision = 'APPROVE' THEN 1 ELSE 0 END) as approved,
                      SUM(CASE WHEN decision = 'DENY' THEN 1 ELSE 0 END) as denied
               FROM decision_history WHERE selected_model = :mid""",
            {"mid": model_id},
        )
        if not rows:
            return {"model_id": model_id, "total": 0}
        r = rows[0]
        total = r["total"] or 0
        return {
            "model_id": model_id,
            "total": total,
            "approved": r["approved"] or 0,
            "denied": r["denied"] or 0,
            "approval_rate": round((r["approved"] or 0) / total, 2) if total > 0 else 0,
        }

    async def count(self) -> int:
        rows = await self._engine.execute("SELECT COUNT(*) as cnt FROM decision_history")
        return rows[0]["cnt"] if rows else 0
