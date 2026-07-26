"""Persistent state transitions preventing logical replay."""

from datetime import datetime, timedelta, timezone

from .state import IdempotencyState, SafetyOperationRecord
from .storage import AuthoritySafetyStorage


class PersistentIdempotencyManager:
    def __init__(self, storage: AuthoritySafetyStorage) -> None:
        self.storage = storage

    def begin(
        self,
        *,
        correlation_id: str,
        migration_state: str,
        fallback_state: str,
        authority_decision: str,
        evidence_hash: str,
        ttl_seconds: int,
    ) -> SafetyOperationRecord:
        existing = self.storage.get(correlation_id)
        if existing is not None:
            if existing.evidence_hash != evidence_hash:
                raise ValueError("evidence hash mismatch")
            return existing
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        now = datetime.now(timezone.utc)
        record = SafetyOperationRecord(
            correlation_id=correlation_id,
            migration_state=migration_state,
            fallback_state=fallback_state,
            authority_decision=authority_decision,
            evidence_hash=evidence_hash,
            state=IdempotencyState.PENDING,
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
        )
        self.storage.insert(record)
        return record

    def transition(
        self,
        correlation_id: str,
        target: IdempotencyState,
    ) -> SafetyOperationRecord:
        record = self.storage.get(correlation_id)
        if record is None:
            raise KeyError("operation not found")
        allowed = {
            IdempotencyState.PENDING: {
                IdempotencyState.COMMITTED,
                IdempotencyState.ROLLED_BACK,
                IdempotencyState.EXPIRED,
            }
        }
        if target is record.state:
            return record
        if target not in allowed.get(record.state, set()):
            raise ValueError("invalid idempotency transition")
        self.storage.update_state(
            correlation_id=correlation_id,
            state=target,
            updated_at=datetime.now(timezone.utc),
        )
        updated = self.storage.get(correlation_id)
        if updated is None:
            raise RuntimeError("persisted state disappeared")
        return updated
