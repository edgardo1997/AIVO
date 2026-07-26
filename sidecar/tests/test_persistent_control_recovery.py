from sentinel.persistent_control_boundary import (
    PersistentControlBoundary,
    PersistentControlState,
    PersistentRecoveryStatus,
)

EVIDENCE_HASH = "d" * 64
ISSUER_ID = "issuer.boundary.v1"
SIGNATURE = "s" * 88


def test_empty_or_terminal_storage_is_recovery_ok(tmp_path):
    boundary = PersistentControlBoundary(
        database_path=tmp_path / "boundary.sqlite3",
        enabled=True,
    )
    assert boundary.recovery.inspect() is PersistentRecoveryStatus.RECOVERY_OK
    boundary.close()


def test_incomplete_state_requires_recovery_without_resuming(tmp_path):
    boundary = PersistentControlBoundary(
        database_path=tmp_path / "boundary.sqlite3",
        enabled=True,
    )
    boundary.transaction.create(
        correlation_id="request-1",
        evidence_hash=EVIDENCE_HASH,
        issuer_id=ISSUER_ID,
        signature=SIGNATURE,
    )

    assert boundary.recovery.inspect() is PersistentRecoveryStatus.RECOVERY_REQUIRED
    assert boundary.transaction.get("request-1").state is PersistentControlState.NEW
    boundary.close()


def test_integrity_failure_blocks_recovery(tmp_path, monkeypatch):
    boundary = PersistentControlBoundary(
        database_path=tmp_path / "boundary.sqlite3",
        enabled=True,
    )
    monkeypatch.setattr(boundary.storage, "integrity_check", lambda: False)

    assert boundary.recovery.inspect() is PersistentRecoveryStatus.RECOVERY_BLOCKED
    boundary.close()
