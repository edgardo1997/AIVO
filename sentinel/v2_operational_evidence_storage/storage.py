"""Transactional SQLite operational evidence storage."""

import sqlite3
from datetime import datetime
from pathlib import Path

from sentinel.contracts import EvidenceSignalV1
from sentinel.evidence_integrity import (
    EvidenceVerificationStatus,
    EvidenceVerifier,
)

from .control import EvidenceStorageControl
from .integrity import EvidenceIntegrityError
from .schema import (
    SCHEMA_SQL,
    SCHEMA_VERSION,
    EvidenceRecordV1,
)


class OperationalEvidenceStorage:
    @classmethod
    def open(
        cls,
        *,
        control: EvidenceStorageControl,
        database_path: Path,
    ) -> "OperationalEvidenceStorage | None":
        if not control.enabled:
            return None
        return cls(database_path)

    def __init__(self, database_path: Path) -> None:
        self._connection = sqlite3.connect(str(database_path))
        self._connection.executescript(SCHEMA_SQL)
        self._migrate_schema()
        self.unclean_start = self._meta("session_dirty") == "1"
        self._set_meta("session_dirty", "1")

    def _migrate_schema(self) -> None:
        current = int(self._meta("schema_version") or "0")
        if current > SCHEMA_VERSION:
            raise RuntimeError("unsupported future schema")
        if current < SCHEMA_VERSION:
            self._set_meta("schema_version", str(SCHEMA_VERSION))

    def close(self) -> None:
        self._set_meta("session_dirty", "0")
        self._connection.close()

    def simulate_unexpected_close(self) -> None:
        self._connection.close()

    def write(self, record: EvidenceRecordV1) -> None:
        if not record.integrity_valid():
            raise EvidenceIntegrityError("record integrity mismatch")
        with self._connection:
            self._connection.execute(
                "INSERT INTO operational_evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.event_id_hash,
                    record.timestamp.isoformat(),
                    record.event_type,
                    record.correlation_hash,
                    record.result_code,
                    record.health_state,
                    record.incident_state,
                    record.integrity_hash,
                ),
            )

    def write_signal(
        self,
        signal: EvidenceSignalV1,
        *,
        verifier: EvidenceVerifier,
    ) -> None:
        verification = verifier.verify(signal)
        if verification.status is not EvidenceVerificationStatus.VERIFIED:
            raise EvidenceIntegrityError(f"signed evidence rejected: {verification.status.value}")
        try:
            with self._connection:
                self._connection.execute(
                    """
                    INSERT INTO signed_evidence(
                        evidence_id, issuer_id, schema_version, created_at,
                        correlation_id, payload_hash, signature, integrity_status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        signal.evidence_id,
                        signal.issuer_id,
                        signal.schema_version,
                        signal.created_at.isoformat(),
                        signal.correlation_id,
                        signal.payload_hash,
                        signal.signature,
                        EvidenceVerificationStatus.VERIFIED.value,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise EvidenceIntegrityError("signed evidence replay detected") from exc

    def read_signal(self, evidence_id: str) -> EvidenceSignalV1 | None:
        row = self._connection.execute(
            """
            SELECT evidence_id, issuer_id, schema_version, created_at,
                   correlation_id, payload_hash, signature, integrity_status
            FROM signed_evidence WHERE evidence_id = ?
            """,
            (evidence_id,),
        ).fetchone()
        if row is None:
            return None
        return EvidenceSignalV1(
            evidence_id=row[0],
            issuer_id=row[1],
            schema_version=row[2],
            created_at=datetime.fromisoformat(row[3]),
            correlation_id=row[4],
            payload_hash=row[5],
            signature=row[6],
            integrity_status=row[7],
        )

    def read(self, event_id_hash: str) -> EvidenceRecordV1 | None:
        row = self._connection.execute(
            "SELECT event_id_hash, timestamp, event_type, correlation_hash, "
            "result_code, health_state, incident_state, integrity_hash "
            "FROM operational_evidence WHERE event_id_hash = ?",
            (event_id_hash,),
        ).fetchone()
        if row is None:
            return None
        record = _record(row)
        if not record.integrity_valid():
            raise EvidenceIntegrityError("persisted record integrity mismatch")
        return record

    def read_all(self) -> tuple[EvidenceRecordV1, ...]:
        rows = self._connection.execute(
            "SELECT event_id_hash, timestamp, event_type, correlation_hash, "
            "result_code, health_state, incident_state, integrity_hash "
            "FROM operational_evidence ORDER BY timestamp"
        ).fetchall()
        records = tuple(_record(row) for row in rows)
        if any(not record.integrity_valid() for record in records):
            raise EvidenceIntegrityError("corrupt record detected")
        return records

    def integrity_ok(self) -> bool:
        row = self._connection.execute("PRAGMA integrity_check").fetchone()
        if not row or row[0] != "ok":
            return False
        try:
            self.read_all()
        except Exception:
            return False
        return True

    def count(self) -> int:
        row = self._connection.execute("SELECT COUNT(*) FROM operational_evidence").fetchone()
        return int(row[0]) if row else 0

    @property
    def connection(self) -> sqlite3.Connection:
        return self._connection

    def _meta(self, key: str) -> str | None:
        row = self._connection.execute(
            "SELECT value FROM storage_meta WHERE key = ?",
            (key,),
        ).fetchone()
        return str(row[0]) if row else None

    def _set_meta(self, key: str, value: str) -> None:
        with self._connection:
            self._connection.execute(
                "INSERT INTO storage_meta(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )


def _record(row: tuple) -> EvidenceRecordV1:
    return EvidenceRecordV1(
        event_id_hash=row[0],
        timestamp=datetime.fromisoformat(row[1]),
        event_type=row[2],
        correlation_hash=row[3],
        result_code=row[4],
        health_state=row[5],
        incident_state=row[6],
        integrity_hash=row[7],
    )
