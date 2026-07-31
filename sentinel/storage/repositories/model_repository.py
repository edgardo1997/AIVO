"""ModelRepository — Persistir modelos descubiertos.

Guarda: nombre, proveedor, tipo, capacidades, disponibilidad, última detección.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from sentinel.storage.database import StorageEngine
from sentinel.storage.models import StoredModel

logger = logging.getLogger(__name__)


class ModelRepository:
    def __init__(self, engine: StorageEngine):
        self._engine = engine

    async def save(self, model: StoredModel) -> None:
        row = model.to_row()
        await self._engine.execute(
            """INSERT OR REPLACE INTO stored_models
               (id, name, provider, local, capabilities, context_size, cost, latency_estimate, last_seen, created_at)
               VALUES (:id, :name, :provider, :local, :capabilities, :context_size, :cost, :latency_estimate, :last_seen, :created_at)""",
            row,
        )

    async def save_batch(self, models: List[StoredModel]) -> None:
        for m in models:
            await self.save(m)

    async def get(self, model_id: str) -> Optional[StoredModel]:
        rows = await self._engine.execute(
            "SELECT * FROM stored_models WHERE id = :id", {"id": model_id}
        )
        if rows:
            return StoredModel.from_row(dict(rows[0]))
        return None

    async def get_by_name(self, name: str, provider: str) -> Optional[StoredModel]:
        rows = await self._engine.execute(
            "SELECT * FROM stored_models WHERE name = :name AND provider = :provider",
            {"name": name, "provider": provider},
        )
        if rows:
            return StoredModel.from_row(dict(rows[0]))
        return None

    async def list_all(self) -> List[StoredModel]:
        rows = await self._engine.execute("SELECT * FROM stored_models ORDER BY name")
        return [StoredModel.from_row(dict(r)) for r in rows]

    async def list_by_provider(self, provider: str) -> List[StoredModel]:
        rows = await self._engine.execute(
            "SELECT * FROM stored_models WHERE provider = :provider ORDER BY name",
            {"provider": provider},
        )
        return [StoredModel.from_row(dict(r)) for r in rows]

    async def list_local(self) -> List[StoredModel]:
        rows = await self._engine.execute(
            "SELECT * FROM stored_models WHERE local = 1 ORDER BY name"
        )
        return [StoredModel.from_row(dict(r)) for r in rows]

    async def update_last_seen(self, model_id: str) -> None:
        from datetime import datetime, timezone
        await self._engine.execute(
            "UPDATE stored_models SET last_seen = :now WHERE id = :id",
            {"id": model_id, "now": datetime.now(timezone.utc).isoformat()},
        )

    async def delete(self, model_id: str) -> bool:
        await self._engine.execute(
            "DELETE FROM stored_models WHERE id = :id", {"id": model_id}
        )
        return True

    async def count(self) -> int:
        rows = await self._engine.execute("SELECT COUNT(*) as cnt FROM stored_models")
        return rows[0]["cnt"] if rows else 0
