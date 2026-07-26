"""Transactional SQLite persistence for events and metric snapshots."""

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator

from .events import OperationalEventV1
from .metrics import OperationalMetricSnapshotV1
from .schema import SCHEMA_SQL, SCHEMA_VERSION


class TelemetryIntegrityError(ValueError):
    pass


class OperationalTelemetryStorage:
    def __init__(self, database_path: Path) -> None:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(
            database_path,
            isolation_level=None,
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.execute("PRAGMA busy_timeout = 5000")
        self._initialize()

    def _initialize(self) -> None:
        with self.transaction() as cursor:
            cursor.executescript(SCHEMA_SQL)
            row = cursor.execute("SELECT version FROM telemetry_schema LIMIT 1").fetchone()
            if row is None:
                cursor.execute(
                    "INSERT INTO telemetry_schema(version) VALUES (?)",
                    (SCHEMA_VERSION,),
                )
            elif int(row["version"]) != SCHEMA_VERSION:
                raise RuntimeError("unsupported telemetry schema version")

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Cursor]:
        cursor = self._connection.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        try:
            yield cursor
        except Exception:
            self._connection.rollback()
            raise
        else:
            self._connection.commit()
        finally:
            cursor.close()

    def write_event(self, event: OperationalEventV1) -> None:
        record_hash = event.canonical_hash()
        with self.transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO operational_events(
                    event_id, correlation_id, evidence_hash, issuer_id,
                    timestamp, event_type, health_state, decision_state,
                    integrity_status, record_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.correlation_id,
                    event.evidence_hash,
                    event.issuer_id,
                    event.timestamp.isoformat(),
                    event.event_type,
                    event.health_state.value,
                    event.decision_state,
                    event.integrity_status.value,
                    record_hash,
                ),
            )
            cursor.execute(
                "INSERT INTO timeline_index(event_id, timestamp) VALUES (?, ?)",
                (event.event_id, event.timestamp.isoformat()),
            )

    def read_event(self, event_id: str) -> OperationalEventV1 | None:
        row = self._connection.execute(
            "SELECT * FROM operational_events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        if row is None:
            return None
        event = _event_from_row(row)
        if event.canonical_hash() != row["record_hash"]:
            raise TelemetryIntegrityError("operational event integrity mismatch")
        return event

    def write_snapshot(self, snapshot: OperationalMetricSnapshotV1) -> None:
        timestamp = datetime.now(UTC).isoformat()
        values = snapshot.model_dump(exclude={"authority", "execution_requested"})
        record_hash = _snapshot_hash(timestamp, values)
        with self.transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO metric_snapshots(
                    timestamp, decisions, divergences, errors, rollbacks,
                    health_transitions, evidence_verified, evidence_rejected,
                    canary_observations, record_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    values["decisions"],
                    values["divergences"],
                    values["errors"],
                    values["rollbacks"],
                    values["health_transitions"],
                    values["evidence_verified"],
                    values["evidence_rejected"],
                    values["canary_observations"],
                    record_hash,
                ),
            )

    @property
    def connection(self) -> sqlite3.Connection:
        return self._connection

    def close(self) -> None:
        self._connection.close()


def _event_from_row(row: sqlite3.Row) -> OperationalEventV1:
    return OperationalEventV1(
        event_id=row["event_id"],
        correlation_id=row["correlation_id"],
        evidence_hash=row["evidence_hash"],
        issuer_id=row["issuer_id"],
        timestamp=datetime.fromisoformat(row["timestamp"]),
        event_type=row["event_type"],
        health_state=row["health_state"],
        decision_state=row["decision_state"],
        integrity_status=row["integrity_status"],
    )


def _snapshot_hash(timestamp: str, values: dict[str, int]) -> str:
    canonical = json.dumps(
        {"timestamp": timestamp, **values},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
