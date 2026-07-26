"""Atomic state transition coordinator."""

import sqlite3
from datetime import UTC, datetime

from .audit import append_audit
from .schema import (
    TERMINAL_STATES,
    VALID_TRANSITIONS,
    PersistentControlRecordV1,
    PersistentControlState,
)
from .storage import PersistentControlStorage


class EvidenceConflictError(ValueError):
    pass


class InvalidTransitionError(ValueError):
    pass


class PersistentControlTransaction:
    def __init__(self, storage: PersistentControlStorage) -> None:
        self.storage = storage

    def create(
        self,
        *,
        correlation_id: str,
        evidence_hash: str,
        issuer_id: str,
        signature: str,
    ) -> PersistentControlRecordV1:
        now = datetime.now(UTC)
        with self.storage.transaction() as cursor:
            row = self._select(cursor, correlation_id)
            if row is not None:
                self._validate_evidence(row, evidence_hash, issuer_id, signature)
                return self._to_record(row)
            audit_id = append_audit(
                cursor,
                event="control_created",
                timestamp=now,
                correlation_id=correlation_id,
                evidence_hash=evidence_hash,
                previous_state=None,
                new_state=PersistentControlState.NEW,
                result="RECORDED",
            )
            cursor.execute(
                """
                INSERT INTO control_records(
                    correlation_id, evidence_hash, issuer_id, signature,
                    state, activation_state, rollback_state, audit_reference,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    correlation_id,
                    evidence_hash,
                    issuer_id,
                    signature,
                    PersistentControlState.NEW.value,
                    "INACTIVE",
                    "NOT_REQUESTED",
                    str(audit_id),
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
            return self._to_record(self._select_required(cursor, correlation_id))

    def transition(
        self,
        *,
        correlation_id: str,
        evidence_hash: str,
        issuer_id: str,
        signature: str,
        target: PersistentControlState,
        activation_state: str | None = None,
        rollback_state: str | None = None,
    ) -> PersistentControlRecordV1:
        now = datetime.now(UTC)
        with self.storage.transaction() as cursor:
            row = self._select_required(cursor, correlation_id)
            self._validate_evidence(row, evidence_hash, issuer_id, signature)
            current = PersistentControlState(row["state"])
            if current is target:
                return self._to_record(row)
            if current in TERMINAL_STATES or target not in VALID_TRANSITIONS.get(current, frozenset()):
                raise InvalidTransitionError(f"invalid transition: {current.value} -> {target.value}")
            next_activation = activation_state or row["activation_state"]
            next_rollback = rollback_state or row["rollback_state"]
            audit_id = append_audit(
                cursor,
                event="state_transition",
                timestamp=now,
                correlation_id=correlation_id,
                evidence_hash=evidence_hash,
                previous_state=current,
                new_state=target,
                result="RECORDED",
            )
            cursor.execute(
                """
                UPDATE control_records
                SET state = ?, activation_state = ?, rollback_state = ?,
                    audit_reference = ?, updated_at = ?
                WHERE correlation_id = ? AND evidence_hash = ? AND state = ?
                """,
                (
                    target.value,
                    next_activation,
                    next_rollback,
                    str(audit_id),
                    now.isoformat(),
                    correlation_id,
                    evidence_hash,
                    current.value,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("concurrent persistent control transition")
            return self._to_record(self._select_required(cursor, correlation_id))

    def get(self, correlation_id: str) -> PersistentControlRecordV1 | None:
        row = self.storage.connection.execute(
            "SELECT * FROM control_records WHERE correlation_id = ?",
            (correlation_id,),
        ).fetchone()
        return None if row is None else self._to_record(row)

    @staticmethod
    def _select(
        cursor: sqlite3.Cursor,
        correlation_id: str,
    ) -> sqlite3.Row | None:
        return cursor.execute(
            "SELECT * FROM control_records WHERE correlation_id = ?",
            (correlation_id,),
        ).fetchone()

    def _select_required(
        self,
        cursor: sqlite3.Cursor,
        correlation_id: str,
    ) -> sqlite3.Row:
        row = self._select(cursor, correlation_id)
        if row is None:
            raise KeyError("persistent control record not found")
        return row

    @staticmethod
    def _validate_evidence(
        row: sqlite3.Row,
        evidence_hash: str,
        issuer_id: str,
        signature: str,
    ) -> None:
        if row["evidence_hash"] != evidence_hash or row["issuer_id"] != issuer_id or row["signature"] != signature:
            raise EvidenceConflictError("correlation_id already reserved with different signed evidence")

    @staticmethod
    def _to_record(row: sqlite3.Row) -> PersistentControlRecordV1:
        return PersistentControlRecordV1(
            correlation_id=row["correlation_id"],
            evidence_hash=row["evidence_hash"],
            issuer_id=row["issuer_id"],
            signature=row["signature"],
            state=row["state"],
            activation_state=row["activation_state"],
            rollback_state=row["rollback_state"],
            audit_reference=row["audit_reference"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
