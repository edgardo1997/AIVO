from datetime import timedelta

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from sentinel.evidence_integrity import (
    EvidenceSigner,
    EvidenceVerificationStatus,
    EvidenceVerifier,
    IssuerIdentityV1,
    IssuerRegistry,
)
from sentinel.final_control_plane_readiness.passive_pipeline import (
    PassivePipelineStatus,
    PassiveV2DecisionPipeline,
)
from sentinel.operational_telemetry_hub import OperationalTelemetryHub
from sentinel.persistent_control_boundary import PersistentControlBoundary


def _pipeline(tmp_path):
    private_key = Ed25519PrivateKey.generate()
    issuer_id = "sentinel.v2.test"
    public_key = private_key.public_key().public_bytes_raw()
    registry = IssuerRegistry(
        (
            IssuerIdentityV1(
                issuer_id=issuer_id,
                public_key=public_key,
                identity_version="1",
            ),
        )
    )
    boundary = PersistentControlBoundary(
        database_path=tmp_path / "control.sqlite3",
        enabled=True,
    )
    telemetry = OperationalTelemetryHub(
        database_path=tmp_path / "telemetry.sqlite3",
        enabled=True,
    )
    pipeline = PassiveV2DecisionPipeline(
        signer=EvidenceSigner(issuer_id=issuer_id, private_key=private_key),
        verifier=EvidenceVerifier(registry, maximum_age=timedelta(minutes=5)),
        persistent_boundary=boundary,
        telemetry_hub=telemetry,
    )
    return pipeline, boundary, telemetry


def test_complete_pipeline_persists_signs_and_records_telemetry(tmp_path):
    pipeline, boundary, telemetry = _pipeline(tmp_path)
    try:
        request = {"request_type": "APPLICATION_LOOKUP"}
        result = pipeline.process(
            decision_state="observe",
            sanitized_request=request,
            confidence=84.0,
        )

        assert result.status is PassivePipelineStatus.COMPLETED
        assert result.authority is False
        assert result.execution_requested is False
        assert result.evidence is not None
        assert result.audit_event is not None
        assert result.operational_event is not None
        assert result.readiness is not None
        assert result.metric_snapshot is not None
        verification = pipeline.verifier.verify(
            result.evidence,
            payload=request,
            detect_replay=False,
        )
        assert verification.status is EvidenceVerificationStatus.VERIFIED

        derived = (
            result.decision,
            result.audit_event,
            result.operational_event,
            result.readiness,
        )
        assert {item.correlation_id for item in derived} == {result.evidence.correlation_id}
        assert {item.evidence_hash for item in derived} == {result.evidence.payload_hash}
        assert {item.issuer_id for item in derived} == {result.evidence.issuer_id}
        assert {item.timestamp for item in derived} == {result.evidence.created_at}

        record = boundary.transaction.get(result.correlation_id)
        assert record is not None
        assert record.evidence_hash == result.evidence.payload_hash
        assert telemetry.timeline.latest() == (result.operational_event,)
        assert result.metric_snapshot.decisions == 1
    finally:
        boundary.close()
        telemetry.close()


def test_each_pipeline_run_has_a_unique_correlation_id(tmp_path):
    pipeline, boundary, telemetry = _pipeline(tmp_path)
    try:
        first = pipeline.process(
            decision_state="observe",
            sanitized_request={"request_type": "LOOKUP"},
            confidence=50,
        )
        second = pipeline.process(
            decision_state="observe",
            sanitized_request={"request_type": "LOOKUP"},
            confidence=50,
        )
        assert first.correlation_id != second.correlation_id
    finally:
        boundary.close()
        telemetry.close()


def test_disabled_persistence_rejects_before_telemetry(tmp_path):
    pipeline, boundary, telemetry = _pipeline(tmp_path)
    boundary.close()
    pipeline.persistent_boundary = PersistentControlBoundary(
        database_path=tmp_path / "disabled.sqlite3",
        enabled=False,
    )
    try:
        result = pipeline.process(
            decision_state="observe",
            sanitized_request={"request_type": "LOOKUP"},
            confidence=50,
        )
        assert result.status is PassivePipelineStatus.PERSISTENCE_REJECTED
        assert result.audit_event is None
        assert result.operational_event is None
        assert result.readiness is None
        assert telemetry.timeline.latest() == ()
        assert not (tmp_path / "disabled.sqlite3").exists()
    finally:
        pipeline.persistent_boundary.close()
        telemetry.close()


def test_signature_rejection_stops_before_persistence_and_telemetry(tmp_path):
    pipeline, boundary, telemetry = _pipeline(tmp_path)

    class RejectingVerifier:
        @staticmethod
        def verify(*args, **kwargs):
            class Result:
                status = EvidenceVerificationStatus.INVALID_SIGNATURE

            return Result()

    pipeline.verifier = RejectingVerifier()
    try:
        result = pipeline.process(
            decision_state="observe",
            sanitized_request={"request_type": "LOOKUP"},
            confidence=50,
        )
        assert result.status is PassivePipelineStatus.SIGNATURE_REJECTED
        assert boundary.transaction.get(result.correlation_id) is None
        assert telemetry.timeline.latest() == ()
        assert result.readiness is None
    finally:
        boundary.close()
        telemetry.close()


def test_persistence_error_rejects_without_fallback_or_telemetry(tmp_path):
    pipeline, boundary, telemetry = _pipeline(tmp_path)

    class FailingTransaction:
        @staticmethod
        def create(**kwargs):
            raise RuntimeError("isolated persistence failure")

    boundary.transaction = FailingTransaction()
    try:
        result = pipeline.process(
            decision_state="observe",
            sanitized_request={"request_type": "LOOKUP"},
            confidence=50,
        )
        assert result.status is PassivePipelineStatus.PERSISTENCE_REJECTED
        assert result.error_code == "RuntimeError"
        assert result.audit_event is None
        assert result.operational_event is None
        assert result.readiness is None
        assert telemetry.timeline.latest() == ()
    finally:
        boundary.close()
        telemetry.close()


def test_sensitive_request_is_rejected_without_persistence(tmp_path):
    pipeline, boundary, telemetry = _pipeline(tmp_path)
    try:
        result = pipeline.process(
            decision_state="observe",
            sanitized_request={"command": "not-allowed"},
            confidence=50,
        )
        assert result.status is PassivePipelineStatus.SIGNATURE_REJECTED
        assert boundary.transaction.get(result.correlation_id) is None
        assert telemetry.timeline.latest() == ()
    finally:
        boundary.close()
        telemetry.close()
