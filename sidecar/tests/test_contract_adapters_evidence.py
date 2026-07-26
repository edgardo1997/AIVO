from datetime import UTC, datetime

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from sentinel.contract_adapters import adapt_audit, adapt_evidence
from sentinel.contracts import AuditEventV1, EvidenceSignalV1
from sentinel.evidence_integrity import EvidenceSigner


def _signal() -> EvidenceSignalV1:
    return EvidenceSigner(
        issuer_id="issuer.adapter.v1",
        private_key=Ed25519PrivateKey.generate(),
    ).sign(payload={"count": 1}, correlation_id="correlation-1")


def test_evidence_adapter_preserves_signed_signal():
    signal = _signal()
    result = adapt_evidence(object(), signal=signal)

    assert result.contract is signal
    assert result.contract.signature == signal.signature
    assert result.metadata.correlation_id == signal.correlation_id
    assert result.contract.authority is False
    assert result.contract.execution_requested is False


def test_audit_adapter_uses_sanitized_values_only():
    timestamp = datetime.now(UTC)
    result = adapt_audit(
        object(),
        correlation_id="correlation-1",
        event_type="canary_observed",
        result="MATCH",
        timestamp=timestamp,
    )

    assert isinstance(result.contract, AuditEventV1)
    assert result.contract.timestamp == timestamp
    assert result.contract.evidence_hash == result.metadata.evidence_hash
