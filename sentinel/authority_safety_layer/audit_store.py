"""Persistent sanitized audit metadata."""

import re
from datetime import datetime, timezone

from .storage import AuthoritySafetyStorage


class AuthorityAuditStore:
    def __init__(self, storage: AuthoritySafetyStorage) -> None:
        self.storage = storage

    def append(self, *, event: str, evidence_hash: str, result: str) -> None:
        for code in (event, result):
            if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", code):
                raise ValueError("audit codes must be sanitized")
        if not re.fullmatch(r"[a-f0-9]{64}", evidence_hash):
            raise ValueError("invalid evidence hash")
        cursor = self.storage.connection.cursor()
        cursor.execute(
            "INSERT INTO safety_audit VALUES (?, ?, ?, ?)",
            (event, datetime.now(timezone.utc).isoformat(), evidence_hash, result),
        )
        self.storage.connection.commit()

    def count(self) -> int:
        cursor = self.storage.connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM safety_audit")
        row = cursor.fetchone()
        return int(row[0]) if row else 0
