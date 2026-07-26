import pytest
from pydantic import ValidationError

from sentinel.v2_operational_evidence_storage import (
    EvidenceRecordV1,
    EvidenceStorageMetrics,
    EvidenceStorageReport,
    RecoveryStatus,
)


def test_record_schema_contains_only_allowed_fields() -> None:
    assert set(EvidenceRecordV1.model_fields) == {
        "event_id_hash",
        "timestamp",
        "event_type",
        "correlation_hash",
        "result_code",
        "health_state",
        "incident_state",
        "integrity_hash",
    }


def test_record_rejects_sensitive_fields() -> None:
    with pytest.raises(ValidationError):
        EvidenceRecordV1(
            event_id_hash="a" * 64,
            timestamp="2026-07-25T00:00:00+00:00",
            event_type="EVENT",
            correlation_hash="b" * 64,
            result_code="OK",
            health_state="HEALTHY",
            incident_state="INCIDENT_NONE",
            integrity_hash="c" * 64,
            prompt="secret",
        )


def test_metrics_and_report_are_aggregate_only() -> None:
    metrics = EvidenceStorageMetrics()
    metrics.increment("total_records", 2)
    metrics.increment("deleted_records")
    snapshot = metrics.snapshot()
    assert snapshot.total_records == 2
    assert snapshot.deleted_records == 1
    assert not hasattr(metrics, "records")
    report = EvidenceStorageReport(
        storage_state="OPEN",
        integrity_valid=True,
        recovery=RecoveryStatus.RECOVERY_OK,
        metrics=snapshot,
        risks=(),
    )
    assert report.human_readable().startswith("SENTINEL V2 OPERATIONAL EVIDENCE STORAGE REPORT")
