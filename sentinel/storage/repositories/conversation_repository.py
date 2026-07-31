"""ConversationRepository — Persistir sesiones y mensajes.

Guarda: sesiones, mensajes, contexto, decisiones relacionadas.
Permite recuperar contexto después de reinicio.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from sentinel.storage.database import StorageEngine
from sentinel.storage.models import ConversationRecord

logger = logging.getLogger(__name__)


class ConversationRepository:
    def __init__(self, engine: StorageEngine):
        self._engine = engine

    async def save_message(self, record: ConversationRecord) -> None:
        row = record.to_row()
        await self._engine.execute(
            """INSERT INTO conversations
               (session_id, message_id, role, content, context, model_id, created_at)
               VALUES (:session_id, :message_id, :role, :content, :context, :model_id, :created_at)""",
            row,
        )

    async def save_batch(self, records: List[ConversationRecord]) -> None:
        for r in records:
            await self.save_message(r)

    async def get_session_messages(self, session_id: str, limit: int = 50) -> List[ConversationRecord]:
        rows = await self._engine.execute(
            "SELECT * FROM conversations WHERE session_id = :sid ORDER BY created_at ASC LIMIT :lim",
            {"sid": session_id, "lim": limit},
        )
        return [ConversationRecord.from_row(dict(r)) for r in rows]

    async def get_latest_session(self, user_id: str) -> Optional[str]:
        rows = await self._engine.execute(
            "SELECT session_id FROM conversations WHERE context LIKE :uid ORDER BY created_at DESC LIMIT 1",
            {"uid": f"%{user_id}%"},
        )
        return rows[0]["session_id"] if rows else None

    async def get_session_context(self, session_id: str) -> Dict[str, Any]:
        rows = await self._engine.execute(
            "SELECT context FROM conversations WHERE session_id = :sid AND context != '{}' ORDER BY created_at DESC LIMIT 1",
            {"sid": session_id},
        )
        if rows:
            ctx = rows[0]["context"]
            if isinstance(ctx, str):
                return json.loads(ctx) if ctx else {}
            return ctx or {}
        return {}

    async def list_sessions(self, limit: int = 20) -> List[Dict[str, Any]]:
        rows = await self._engine.execute(
            """SELECT session_id, COUNT(*) as msg_count, MIN(created_at) as first_msg, MAX(created_at) as last_msg
               FROM conversations GROUP BY session_id ORDER BY last_msg DESC LIMIT :lim""",
            {"lim": limit},
        )
        return [dict(r) for r in rows]

    async def delete_session(self, session_id: str) -> bool:
        await self._engine.execute(
            "DELETE FROM conversations WHERE session_id = :sid",
            {"sid": session_id},
        )
        return True

    async def count_sessions(self) -> int:
        rows = await self._engine.execute(
            "SELECT COUNT(DISTINCT session_id) as cnt FROM conversations"
        )
        return rows[0]["cnt"] if rows else 0

    async def count_messages(self) -> int:
        rows = await self._engine.execute("SELECT COUNT(*) as cnt FROM conversations")
        return rows[0]["cnt"] if rows else 0
