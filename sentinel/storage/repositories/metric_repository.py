"""MetricRepository — Persistir métricas de rendimiento.

Guarda: CPU, RAM, GPU, latencia, tokens, costo, errores.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sentinel.storage.database import StorageEngine
from sentinel.storage.models import MetricRecord

logger = logging.getLogger(__name__)


class MetricRepository:
    def __init__(self, engine: StorageEngine):
        self._engine = engine

    async def save(self, record: MetricRecord) -> None:
        row = record.to_row()
        await self._engine.execute(
            """INSERT INTO metric_records
               (id, component, metric_name, value, unit, tags, timestamp)
               VALUES (:id, :component, :metric_name, :value, :unit, :tags, :timestamp)""",
            row,
        )

    async def save_batch(self, records: List[MetricRecord]) -> None:
        for r in records:
            await self.save(r)

    async def get_component_metrics(
        self, component: str, metric_name: Optional[str] = None, limit: int = 100
    ) -> List[MetricRecord]:
        if metric_name:
            rows = await self._engine.execute(
                "SELECT * FROM metric_records WHERE component = :cmp AND metric_name = :mn ORDER BY timestamp DESC LIMIT :lim",
                {"cmp": component, "mn": metric_name, "lim": limit},
            )
        else:
            rows = await self._engine.execute(
                "SELECT * FROM metric_records WHERE component = :cmp ORDER BY timestamp DESC LIMIT :lim",
                {"cmp": component, "lim": limit},
            )
        return [MetricRecord.from_row(dict(r)) for r in rows]

    async def get_average(self, component: str, metric_name: str) -> float:
        rows = await self._engine.execute(
            "SELECT AVG(value) as avg_val FROM metric_records WHERE component = :cmp AND metric_name = :mn",
            {"cmp": component, "mn": metric_name},
        )
        return rows[0]["avg_val"] or 0.0 if rows else 0.0

    async def get_stats(self, component: str, metric_name: str) -> Dict[str, float]:
        rows = await self._engine.execute(
            """SELECT AVG(value) as mean, MIN(value) as min, MAX(value) as max, COUNT(*) as count
               FROM metric_records WHERE component = :cmp AND metric_name = :mn""",
            {"cmp": component, "mn": metric_name},
        )
        if not rows:
            return {"mean": 0, "min": 0, "max": 0, "count": 0}
        r = rows[0]
        return {
            "mean": round(r["mean"] or 0, 2),
            "min": round(r["min"] or 0, 2),
            "max": round(r["max"] or 0, 2),
            "count": r["count"] or 0,
        }

    async def get_latest(self, component: str, metric_name: str) -> Optional[MetricRecord]:
        rows = await self._engine.execute(
            "SELECT * FROM metric_records WHERE component = :cmp AND metric_name = :mn ORDER BY timestamp DESC LIMIT 1",
            {"cmp": component, "mn": metric_name},
        )
        if rows:
            return MetricRecord.from_row(dict(rows[0]))
        return None

    async def list_components(self) -> List[str]:
        rows = await self._engine.execute(
            "SELECT DISTINCT component FROM metric_records ORDER BY component"
        )
        return [r["component"] for r in rows]

    async def delete_older_than(self, days: int) -> int:
        from datetime import datetime, timedelta, timezone
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        await self._engine.execute(
            "DELETE FROM metric_records WHERE timestamp < :cutoff",
            {"cutoff": cutoff},
        )
        return 0

    async def count(self) -> int:
        rows = await self._engine.execute("SELECT COUNT(*) as cnt FROM metric_records")
        return rows[0]["cnt"] if rows else 0
