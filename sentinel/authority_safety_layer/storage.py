"""Transactional SQLite storage limited to sanitized safety metadata."""

import sqlite3
from datetime import datetime
from pathlib import Path

from .state import IdempotencyState, SafetyOperationRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS safety_operations (
    correlation_id TEXT PRIMARY KEY,
    migration_state TEXT NOT NULL,
    fallback_state TEXT NOT NULL,
    authority_decision TEXT NOT NULL,
    evidence_hash TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS safety_audit (
    event TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    evidence_hash TEXT NOT NULL,
    result TEXT NOT NULL
);
"""


class AuthoritySafetyStorage:
    def __init__(self, database_path: Path) -> None:
        self._connection = sqlite3.connect(str(database_path))
        self._connection.executescript(_SCHEMA)
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def integrity_ok(self) -> bool:
        cursor = self._connection.cursor()
        cursor.execute("PRAGMA integrity_check")
        row = cursor.fetchone()
        return bool(row and row[0] == "ok")

    def get(self, correlation_id: str) -> SafetyOperationRecord | None:
        cursor = self._connection.cursor()
        cursor.execute(
            "SELECT correlation_id, migration_state, fallback_state, "
            "authority_decision, evidence_hash, state, created_at, updated_at, "
            "expires_at FROM safety_operations WHERE correlation_id = ?",
            (correlation_id,),
        )
        row = cursor.fetchone()
        return _record(row) if row else None

    def insert(self, record: SafetyOperationRecord) -> None:
        cursor = self._connection.cursor()
        cursor.execute(
            "INSERT INTO safety_operations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            _record_values(record),
        )
        self._connection.commit()

    def update_state(
        self,
        *,
        correlation_id: str,
        state: IdempotencyState,
        updated_at: datetime,
    ) -> None:
        cursor = self._connection.cursor()
        cursor.execute(
            "UPDATE safety_operations SET state = ?, updated_at = ? WHERE correlation_id = ?",
            (state.value, updated_at.isoformat(), correlation_id),
        )
        self._connection.commit()

    def pending(self) -> tuple[SafetyOperationRecord, ...]:
        cursor = self._connection.cursor()
        cursor.execute(
            "SELECT correlation_id, migration_state, fallback_state, "
            "authority_decision, evidence_hash, state, created_at, updated_at, "
            "expires_at FROM safety_operations WHERE state = 'PENDING'"
        )
        return tuple(_record(row) for row in cursor.fetchall())

    @property
    def connection(self) -> sqlite3.Connection:
        return self._connection


def _record(row: tuple) -> SafetyOperationRecord:
    return SafetyOperationRecord(
        correlation_id=row[0],
        migration_state=row[1],
        fallback_state=row[2],
        authority_decision=row[3],
        evidence_hash=row[4],
        state=row[5],
        created_at=datetime.fromisoformat(row[6]),
        updated_at=datetime.fromisoformat(row[7]),
        expires_at=datetime.fromisoformat(row[8]),
    )


def _record_values(record: SafetyOperationRecord) -> tuple[str, ...]:
    return (
        record.correlation_id,
        record.migration_state,
        record.fallback_state,
        record.authority_decision,
        record.evidence_hash,
        record.state.value,
        record.created_at.isoformat(),
        record.updated_at.isoformat(),
        record.expires_at.isoformat(),
    )
