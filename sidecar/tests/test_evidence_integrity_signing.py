from datetime import UTC, datetime

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from sentinel.contracts import EvidenceIntegrityStatusV1
from sentinel.evidence_integrity import EvidenceSigner, canonical_payload_hash


def test_ed25519_signing_produces_payload_free_evidence():
    signer = EvidenceSigner(
        issuer_id="issuer.test.v1",
        private_key=Ed25519PrivateKey.generate(),
    )
    signal = signer.sign(
        payload={"event_type": "POLICY_MATCH", "count": 3},
        correlation_id="correlation-1",
        created_at=datetime.now(UTC),
        evidence_id="evidence-1",
    )

    assert signal.integrity_status is EvidenceIntegrityStatusV1.SIGNED
    assert signal.authority is False
    assert signal.execution_requested is False
    assert signal.payload_hash == canonical_payload_hash({"event_type": "POLICY_MATCH", "count": 3})
    assert not hasattr(signal, "payload")
    assert not hasattr(signal, "private_key")


@pytest.mark.parametrize(
    "payload",
    [
        {"prompt": "private"},
        {"nested": {"command": "unsafe"}},
        {"token": "secret"},
        {"path": "C:/private"},
        {"arguments": ["--unsafe"]},
    ],
)
def test_sensitive_payload_fields_are_rejected(payload):
    signer = EvidenceSigner(
        issuer_id="issuer.test.v1",
        private_key=Ed25519PrivateKey.generate(),
    )
    with pytest.raises(ValueError):
        signer.sign(payload=payload, correlation_id="correlation-1")


def test_evidence_contract_rejects_authority():
    signer = EvidenceSigner(
        issuer_id="issuer.test.v1",
        private_key=Ed25519PrivateKey.generate(),
    )
    signal = signer.sign(payload={"count": 1}, correlation_id="correlation-1")
    values = signal.model_dump()
    values["authority"] = True
    with pytest.raises(ValidationError):
        type(signal)(**values)
