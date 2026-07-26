from datetime import datetime, timezone

import pytest

from sentinel.v2_operational_evidence_storage import (
    EvidenceIntegrityError,
    EvidenceRecordV1,
    EvidenceStorageControl,
    OperationalEvidenceStorage,
)


def record():
    return EvidenceRecordV1.create(
        event_id_hash="a" * 64,
        timestamp=datetime.now(timezone.utc),
        event_type="HEALTH_WARNING",
        correlation_hash="b" * 64,
        result_code="WARNING",
        health_state="WARNING",
        incident_state="INCIDENT_WARNING",
    )


def test_canonical_hash_is_stable() -> None:
    item = record()
    reconstructed = EvidenceRecordV1.create(
        event_id_hash=item.event_id_hash,
        timestamp=item.timestamp,
        event_type=item.event_type,
        correlation_hash=item.correlation_hash,
        result_code=item.result_code,
        health_state=item.health_state,
        incident_state=item.incident_state,
    )
    assert reconstructed.integrity_hash == item.integrity_hash
    assert reconstructed.integrity_valid()


def test_modified_record_is_detected_before_write(tmp_path) -> None:
    storage = OperationalEvidenceStorage.open(
        control=EvidenceStorageControl(enabled=True),
        database_path=tmp_path / "modified.db",
    )
    modified = record().model_copy(update={"result_code": "ALTERED"})
    with pytest.raises(EvidenceIntegrityError):
        storage.write(modified)
    storage.close()


def test_persisted_tampering_is_detected_before_read(tmp_path) -> None:
    storage = OperationalEvidenceStorage.open(
        control=EvidenceStorageControl(enabled=True),
        database_path=tmp_path / "tampered.db",
    )
    item = record()
    storage.write(item)
    storage.connection.execute("UPDATE operational_evidence SET result_code = 'ALTERED'")
    storage.connection.commit()
    with pytest.raises(EvidenceIntegrityError):
        storage.read(item.event_id_hash)
    assert not storage.integrity_ok()
    storage.close()
