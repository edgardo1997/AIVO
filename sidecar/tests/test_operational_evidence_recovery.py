from datetime import datetime, timezone

from sentinel.v2_operational_evidence_storage import (
    EvidenceRecordV1,
    EvidenceStorageControl,
    OperationalEvidenceStorage,
    RecoveryManager,
    RecoveryStatus,
)


def test_clean_close_reports_recovery_ok(tmp_path) -> None:
    database = tmp_path / "clean.db"
    storage = OperationalEvidenceStorage.open(
        control=EvidenceStorageControl(enabled=True),
        database_path=database,
    )
    storage.close()
    reopened = OperationalEvidenceStorage.open(
        control=EvidenceStorageControl(enabled=True),
        database_path=database,
    )
    assert RecoveryManager().inspect(reopened) is RecoveryStatus.RECOVERY_OK
    reopened.close()


def test_unexpected_close_requires_recovery_without_data_loss(tmp_path) -> None:
    database = tmp_path / "unexpected.db"
    storage = OperationalEvidenceStorage.open(
        control=EvidenceStorageControl(enabled=True),
        database_path=database,
    )
    item = EvidenceRecordV1.create(
        event_id_hash="c" * 64,
        timestamp=datetime.now(timezone.utc),
        event_type="ROLLBACK_TRIGGERED",
        correlation_hash="d" * 64,
        result_code="RECORDED",
        health_state="DEGRADED",
        incident_state="INCIDENT_ROLLBACK_REQUIRED",
    )
    storage.write(item)
    storage.simulate_unexpected_close()

    reopened = OperationalEvidenceStorage.open(
        control=EvidenceStorageControl(enabled=True),
        database_path=database,
    )
    assert RecoveryManager().inspect(reopened) is RecoveryStatus.RECOVERY_REQUIRED
    assert reopened.read(item.event_id_hash) == item
    reopened.close()


def test_corrupt_record_blocks_recovery(tmp_path) -> None:
    storage = OperationalEvidenceStorage.open(
        control=EvidenceStorageControl(enabled=True),
        database_path=tmp_path / "corrupt.db",
    )
    storage.connection.execute(
        "INSERT INTO operational_evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "e" * 64,
            datetime.now(timezone.utc).isoformat(),
            "EVENT",
            "f" * 64,
            "OK",
            "HEALTHY",
            "INCIDENT_NONE",
            "0" * 64,
        ),
    )
    storage.connection.commit()
    assert RecoveryManager().inspect(storage) is RecoveryStatus.RECOVERY_BLOCKED
    storage.close()
