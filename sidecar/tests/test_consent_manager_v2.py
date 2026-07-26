from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from sentinel.consent_manager import ConsentManagerControl, ConsentManagerV2
from sentinel.consent_manager.validation import ConsentValidationError
from sentinel.contracts import (
    ConsentDecisionValueV1,
    EvidenceIntegrityStatusV1,
)
from sentinel.evidence_integrity import (
    EvidenceSigner,
    EvidenceVerifier,
    IssuerIdentityV1,
    IssuerRegistry,
)
from sentinel.operational_telemetry_hub import OperationalTelemetryHub
from sentinel.policy_engine import PassivePolicyEngine, PolicyEngineControl
from test_policy_engine_passive import _policy_inputs


def _signed_policy_inputs(tmp_path):
    values = _policy_inputs(tmp_path)
    private_key = Ed25519PrivateKey.generate()
    issuer_id = "sentinel.v2.test"
    registry = IssuerRegistry(
        (
            IssuerIdentityV1(
                issuer_id=issuer_id,
                public_key=private_key.public_key().public_bytes_raw(),
                identity_version="1",
            ),
        )
    )
    verifier = EvidenceVerifier(
        registry,
        maximum_age=timedelta(days=1000),
    )
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    correlation_id = values["simulation"].correlation_id
    evidence = (
        EvidenceSigner(
            issuer_id=issuer_id,
            private_key=private_key,
        )
        .sign(
            payload={"request_type": "DELETE_FILE"},
            correlation_id=correlation_id,
            created_at=timestamp,
            evidence_id="evidence:consent",
        )
        .model_copy(update={"integrity_status": EvidenceIntegrityStatusV1.VERIFIED})
    )
    values["evidence"] = evidence
    values["simulation"] = values["simulation"].model_copy(
        update={
            "evidence_hash": evidence.payload_hash,
            "issuer_id": issuer_id,
            "timestamp": timestamp,
        }
    )
    values["recommendation"] = values["recommendation"].model_copy(
        update={
            "evidence_hash": evidence.payload_hash,
            "issuer_id": issuer_id,
            "timestamp": timestamp,
        }
    )
    values["readiness"] = values["readiness"].model_copy(update={"evidence_hash": evidence.payload_hash})
    policy_telemetry = OperationalTelemetryHub(
        database_path=tmp_path / "policy-consent.sqlite3",
        enabled=True,
    )
    policy_engine = PassivePolicyEngine(
        control=PolicyEngineControl(enabled=True),
        telemetry_hub=policy_telemetry,
    )
    policy = policy_engine.evaluate(**values).evaluation
    policy_telemetry.close()
    return values, policy, verifier


def _manager(tmp_path, verifier, *, enabled=True):
    telemetry = OperationalTelemetryHub(
        database_path=tmp_path / "consent.sqlite3",
        enabled=True,
    )
    manager = ConsentManagerV2(
        control=ConsentManagerControl(enabled=enabled),
        verifier=verifier,
        telemetry_hub=telemetry,
    )
    return manager, telemetry


def _request(manager, values, policy, *, minutes=10):
    now = datetime(2026, 1, 1, 0, 1, tzinfo=UTC)
    return manager.request(
        policy=policy,
        simulation=values["simulation"],
        recommendation=values["recommendation"],
        evidence=values["evidence"],
        readiness=values["readiness"],
        expiration_time=now + timedelta(minutes=minutes),
        now=now,
    )


def test_request_is_pending_and_never_auto_approved(tmp_path):
    values, policy, verifier = _signed_policy_inputs(tmp_path)
    manager, telemetry = _manager(tmp_path, verifier)
    try:
        operation = _request(manager, values, policy)
        assert operation.consent.decision is (ConsentDecisionValueV1.CONSENT_PENDING)
        assert operation.consent.decision_source == "consent-manager"
        assert operation.consent.authority is False
        assert operation.consent.execution_requested is False
    finally:
        telemetry.close()


def test_explicit_human_grant_and_denial(tmp_path):
    values, policy, verifier = _signed_policy_inputs(tmp_path)
    manager, telemetry = _manager(tmp_path, verifier)
    try:
        pending = _request(manager, values, policy).consent
        granted = manager.decide(
            pending.consent_id,
            decision=ConsentDecisionValueV1.CONSENT_GRANTED,
            decision_source="human:reviewer",
            now=pending.timestamp + timedelta(minutes=1),
        ).consent
        assert granted.decision is ConsentDecisionValueV1.CONSENT_GRANTED

        second_manager, second_telemetry = _manager(
            tmp_path / "denial",
            verifier,
        )
        try:
            second = _request(second_manager, values, policy).consent
            denied = second_manager.decide(
                second.consent_id,
                decision=ConsentDecisionValueV1.CONSENT_DENIED,
                decision_source="human:reviewer",
                now=second.timestamp + timedelta(minutes=1),
            ).consent
            assert denied.decision is ConsentDecisionValueV1.CONSENT_DENIED
        finally:
            second_telemetry.close()
    finally:
        telemetry.close()


def test_expiration_invalidates_pending_consent(tmp_path):
    values, policy, verifier = _signed_policy_inputs(tmp_path)
    manager, telemetry = _manager(tmp_path, verifier)
    try:
        pending = _request(manager, values, policy, minutes=1).consent
        expired = manager.get(
            pending.consent_id,
            now=pending.expiration_time + timedelta(seconds=1),
        ).consent
        assert expired.decision is ConsentDecisionValueV1.CONSENT_EXPIRED
    finally:
        telemetry.close()


def test_manual_revocation_records_reason_and_audit(tmp_path):
    values, policy, verifier = _signed_policy_inputs(tmp_path)
    manager, telemetry = _manager(tmp_path, verifier)
    try:
        pending = _request(manager, values, policy).consent
        granted = manager.decide(
            pending.consent_id,
            decision=ConsentDecisionValueV1.CONSENT_GRANTED,
            decision_source="human:reviewer",
            now=pending.timestamp + timedelta(minutes=1),
        ).consent
        operation = manager.revoke(
            granted.consent_id,
            decision_source="human:reviewer",
            reason="USER_REQUEST",
            now=granted.timestamp + timedelta(minutes=1),
        )
        assert operation.consent.decision is (ConsentDecisionValueV1.CONSENT_REVOKED)
        assert operation.consent.revoked is True
        record = manager.revocation_record(granted.consent_id)
        assert record.reason == "USER_REQUEST"
        assert operation.audit_event.result == "CONSENT_REVOKED"
    finally:
        telemetry.close()


def test_invalid_signature_and_correlation_mismatch_are_rejected(tmp_path):
    values, policy, verifier = _signed_policy_inputs(tmp_path)
    manager, telemetry = _manager(tmp_path, verifier)
    try:
        invalid_values = dict(values)
        invalid_values["evidence"] = values["evidence"].model_copy(update={"signature": "B" * 88})
        with pytest.raises(ConsentValidationError, match="signature rejected"):
            _request(manager, invalid_values, policy)

        mismatched_policy = policy.model_copy(update={"correlation_id": "decision:different"})
        with pytest.raises(ConsentValidationError, match="correlation mismatch"):
            _request(manager, values, mismatched_policy)
    finally:
        telemetry.close()


def test_contract_is_immutable_and_human_source_is_required(tmp_path):
    values, policy, verifier = _signed_policy_inputs(tmp_path)
    manager, telemetry = _manager(tmp_path, verifier)
    try:
        pending = _request(manager, values, policy).consent
        with pytest.raises(ValidationError):
            pending.confidence = 0
        with pytest.raises(ValidationError, match="human source"):
            manager.decide(
                pending.consent_id,
                decision=ConsentDecisionValueV1.CONSENT_GRANTED,
                decision_source="automatic",
                now=pending.timestamp + timedelta(minutes=1),
            )
    finally:
        telemetry.close()


def test_every_transition_is_recorded_in_telemetry(tmp_path):
    values, policy, verifier = _signed_policy_inputs(tmp_path)
    manager, telemetry = _manager(tmp_path, verifier)
    try:
        pending_operation = _request(manager, values, policy)
        grant_operation = manager.decide(
            pending_operation.consent.consent_id,
            decision=ConsentDecisionValueV1.CONSENT_GRANTED,
            decision_source="human:reviewer",
            now=pending_operation.consent.timestamp + timedelta(minutes=1),
        )
        assert telemetry.timeline.latest() == (
            pending_operation.operational_event,
            grant_operation.operational_event,
        )
        assert grant_operation.telemetry_snapshot is not None
        assert grant_operation.consent.correlation_id == policy.correlation_id
        assert grant_operation.consent.evidence_hash == policy.evidence_hash
    finally:
        telemetry.close()
