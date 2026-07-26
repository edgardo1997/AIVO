from datetime import UTC, datetime, timedelta

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from sentinel.evidence_integrity import (
    EvidenceSigner,
    EvidenceVerificationStatus,
    EvidenceVerifier,
    IssuerIdentityV1,
    IssuerRegistry,
)


def _system():
    private_key = Ed25519PrivateKey.generate()
    identity = IssuerIdentityV1(
        issuer_id="issuer.test.v1",
        public_key=private_key.public_key().public_bytes_raw(),
        identity_version="1",
    )
    signer = EvidenceSigner(
        issuer_id=identity.issuer_id,
        private_key=private_key,
    )
    return signer, EvidenceVerifier(IssuerRegistry((identity,)))


def test_valid_signature_and_payload_are_verified():
    signer, verifier = _system()
    payload = {"event_type": "POLICY_MATCH", "count": 1}
    signal = signer.sign(payload=payload, correlation_id="correlation-1")

    result = verifier.verify(signal, payload=payload)

    assert result.status is EvidenceVerificationStatus.VERIFIED
    assert result.authority is False
    assert result.execution_requested is False


def test_modified_payload_is_rejected():
    signer, verifier = _system()
    signal = signer.sign(payload={"count": 1}, correlation_id="correlation-1")

    result = verifier.verify(signal, payload={"count": 2})

    assert result.status is EvidenceVerificationStatus.HASH_MISMATCH


def test_modified_signed_metadata_is_rejected():
    signer, verifier = _system()
    signal = signer.sign(payload={"count": 1}, correlation_id="correlation-1")
    modified = signal.model_copy(update={"correlation_id": "correlation-2"})

    result = verifier.verify(modified)

    assert result.status is EvidenceVerificationStatus.INVALID_SIGNATURE


def test_unknown_issuer_and_replay_are_rejected():
    signer, verifier = _system()
    signal = signer.sign(payload={"count": 1}, correlation_id="correlation-1")
    unknown = signal.model_copy(update={"issuer_id": "unknown.issuer"})
    assert verifier.verify(unknown).status is EvidenceVerificationStatus.UNKNOWN_ISSUER
    assert verifier.verify(signal).status is EvidenceVerificationStatus.VERIFIED
    assert verifier.verify(signal).status is EvidenceVerificationStatus.REPLAY_DETECTED


def test_expired_evidence_is_rejected():
    signer, verifier = _system()
    created_at = datetime.now(UTC) - timedelta(days=2)
    signal = signer.sign(
        payload={"count": 1},
        correlation_id="correlation-1",
        created_at=created_at,
    )

    assert verifier.verify(signal, now=datetime.now(UTC)).status is EvidenceVerificationStatus.EXPIRED
