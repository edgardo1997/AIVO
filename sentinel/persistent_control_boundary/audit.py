"""Sanitized persistent audit ledger."""

import sqlite3
from datetime import datetime

from .schema import PersistentControlState


def append_audit(
    cursor: sqlite3.Cursor,
    *,
    event: str,
    timestamp: datetime,
    correlation_id: str,
    evidence_hash: str,
    previous_state: PersistentControlState | None,
    new_state: PersistentControlState,
    result: str,
) -> int:
    cursor.execute(
        """
        INSERT INTO control_audit(
            event, timestamp, correlation_id, evidence_hash,
            previous_state, new_state, result
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event,
            timestamp.isoformat(),
            correlation_id,
            evidence_hash,
            previous_state.value if previous_state else None,
            new_state.value,
            result,
        ),
    )
    return int(cursor.lastrowid)


def count_audit_rows(cursor: sqlite3.Cursor) -> int:
    row = cursor.execute("SELECT COUNT(*) FROM control_audit").fetchone()
    return int(row[0])
