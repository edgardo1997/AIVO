"""UserPreferenceRepository — Memoria de preferencias de usuario.

Guarda preferencias aprendidas: response_style, preferred_models,
privacy_preferences, confirmation_behavior, workflow_patterns (FASE 5.7).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sentinel.storage.database import StorageEngine
from sentinel.storage.models import UserPreference

logger = logging.getLogger(__name__)


class UserPreferenceRepository:
    def __init__(self, engine: StorageEngine):
        self._engine = engine

    async def save(self, pref: UserPreference) -> None:
        row = pref.to_row()
        await self._engine.execute(
            """INSERT INTO intelligence_user_preferences
               (user_id, key, value, source, evidence_count, confidence, created_at, updated_at)
               VALUES (:user_id, :key, :value, :source, :evidence_count, :confidence, :created_at, :updated_at)
               ON CONFLICT(user_id, key) DO UPDATE SET
                 value = excluded.value, source = excluded.source,
                 evidence_count = excluded.evidence_count, confidence = excluded.confidence,
                 updated_at = excluded.updated_at""",
            row,
        )

    async def get(self, user_id: str, key: str) -> Optional[UserPreference]:
        rows = await self._engine.execute(
            "SELECT * FROM intelligence_user_preferences WHERE user_id = :uid AND key = :key",
            {"uid": user_id, "key": key},
        )
        if rows:
            return UserPreference.from_row(dict(rows[0]))
        return None

    async def list_user(self, user_id: str) -> List[UserPreference]:
        rows = await self._engine.execute(
            "SELECT * FROM intelligence_user_preferences WHERE user_id = :uid ORDER BY confidence DESC, key ASC",
            {"uid": user_id},
        )
        return [UserPreference.from_row(dict(r)) for r in rows]

    async def list_all(self) -> List[UserPreference]:
        rows = await self._engine.execute(
            "SELECT * FROM intelligence_user_preferences ORDER BY user_id, key"
        )
        return [UserPreference.from_row(dict(r)) for r in rows]

    async def delete(self, user_id: str, key: str) -> bool:
        await self._engine.execute(
            "DELETE FROM intelligence_user_preferences WHERE user_id = :uid AND key = :key",
            {"uid": user_id, "key": key},
        )
        return True

    async def count(self) -> int:
        rows = await self._engine.execute("SELECT COUNT(*) as cnt FROM intelligence_user_preferences")
        return rows[0]["cnt"] if rows else 0

