from datetime import datetime, timezone

from sentinel.v2_operational_evidence_storage import (
    V2_OPERATIONAL_EVIDENCE_STORAGE_ENABLED,
    EvidenceRecordV1,
    EvidenceRetentionPolicy,
    EvidenceStorageControl,
    OperationalEvidenceStorage,
)


def record(index=1, incident="INCIDENT_NONE"):
    return EvidenceRecordV1.create(
        event_id_hash=f"{index:064x}",
        timestamp=datetime.now(timezone.utc),
        event_type="CANARY_OBSERVATION",
        correlation_hash=f"{index + 100:064x}",
        result_code="OBSERVED",
        health_state="HEALTHY",
        incident_state=incident,
    )


def test_disabled_by_default_creates_no_database(tmp_path) -> None:
    database = tmp_path / "disabled.db"
    assert V2_OPERATIONAL_EVIDENCE_STORAGE_ENABLED is False
    storage = OperationalEvidenceStorage.open(
        control=EvidenceStorageControl(environ={}),
        database_path=database,
    )
    assert storage is None
    assert not database.exists()


def test_transactional_write_and_reopen(tmp_path) -> None:
    database = tmp_path / "evidence.db"
    storage = OperationalEvidenceStorage.open(
        control=EvidenceStorageControl(enabled=True),
        database_path=database,
    )
    item = record()
    storage.write(item)
    assert storage.read(item.event_id_hash) == item
    storage.close()

    reopened = OperationalEvidenceStorage.open(
        control=EvidenceStorageControl(enabled=True),
        database_path=database,
    )
    assert reopened.read(item.event_id_hash) == item
    assert reopened.count() == 1
    reopened.close()


def test_retention_preserves_critical_events(tmp_path) -> None:
    storage = OperationalEvidenceStorage.open(
        control=EvidenceStorageControl(enabled=True),
        database_path=tmp_path / "retention.db",
    )
    storage.write(record(1))
    storage.write(record(2))
    critical = record(3, "INCIDENT_CRITICAL")
    storage.write(critical)
    deleted = EvidenceRetentionPolicy(maximum_records=2).apply(storage)
    assert deleted == 1
    assert storage.read(critical.event_id_hash) == critical
    assert storage.count() == 2
    storage.close()
