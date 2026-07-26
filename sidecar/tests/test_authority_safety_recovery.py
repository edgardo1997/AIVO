from sentinel.authority_safety_layer import (
    AuthoritySafetyStorage,
    IdempotencyState,
    PersistentIdempotencyManager,
    RecoveryManager,
    RecoveryStatus,
)


def test_clean_storage_is_safe(tmp_path) -> None:
    storage = AuthoritySafetyStorage(tmp_path / "clean.db")
    assert RecoveryManager().inspect(storage) is RecoveryStatus.SAFE_RECOVERY
    storage.close()


def test_unexpected_close_with_pending_state_requires_recovery(tmp_path) -> None:
    database = tmp_path / "pending.db"
    storage = AuthoritySafetyStorage(database)
    PersistentIdempotencyManager(storage).begin(
        correlation_id="corr_pending",
        migration_state="LIMITED_CANARY",
        fallback_state="PENDING",
        authority_decision="V2_LIMITED",
        evidence_hash="e" * 64,
        ttl_seconds=60,
    )
    storage.close()

    reopened = AuthoritySafetyStorage(database)
    assert RecoveryManager().inspect(reopened) is RecoveryStatus.RECOVERY_REQUIRED
    record = reopened.get("corr_pending")
    assert record is not None
    assert record.state is IdempotencyState.PENDING
    reopened.close()


def test_corruption_or_storage_failure_blocks_recovery() -> None:
    class CorruptStorage:
        def integrity_ok(self):
            return False

    class BrokenStorage:
        def integrity_ok(self):
            raise RuntimeError("corrupt")

    recovery = RecoveryManager()
    assert recovery.inspect(CorruptStorage()) is RecoveryStatus.BLOCKED_RECOVERY
    assert recovery.inspect(BrokenStorage()) is RecoveryStatus.BLOCKED_RECOVERY
