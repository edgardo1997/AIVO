from datetime import UTC, datetime

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from sentinel.contracts import EvidenceSignalV1
from sentinel.evidence_integrity import EvidenceSigner


def _signal() -> EvidenceSignalV1:
    return EvidenceSigner(
        issuer_id="issuer.contract.v1",
        private_key=Ed25519PrivateKey.generate(),
    ).sign(
        payload={"event_type": "CONTRACT_TEST"},
        correlation_id="correlation-1",
        created_at=datetime.now(UTC),
        evidence_id="evidence-1",
    )


def test_evidence_signal_is_payload_free_and_non_authoritative():
    signal = _signal()

    assert signal.authority is False
    assert signal.execution_requested is False
    assert not hasattr(signal, "payload")
    assert not hasattr(signal, "command")
    assert not hasattr(signal, "arguments")


def test_evidence_signal_requires_timezone_aware_timestamp():
    values = _signal().model_dump()
    values["created_at"] = datetime.now()
    with pytest.raises(ValidationError):
        EvidenceSignalV1(**values)


def test_evidence_signal_is_immutable():
    signal = _signal()

    with pytest.raises(ValidationError):
        signal.payload_hash = "changed"
