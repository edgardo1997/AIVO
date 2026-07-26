import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from sentinel.evidence_integrity import (
    EvidenceSigner,
    EvidenceVerifier,
    IssuerIdentityV1,
    IssuerRegistry,
)
from sentinel.v2_operational_evidence_storage import (
    EvidenceIntegrityError,
    EvidenceStorageControl,
    OperationalEvidenceStorage,
)


def _signed_system():
    private_key = Ed25519PrivateKey.generate()
    identity = IssuerIdentityV1(
        issuer_id="issuer.storage.v1",
        public_key=private_key.public_key().public_bytes_raw(),
        identity_version="1",
    )
    signer = EvidenceSigner(
        issuer_id=identity.issuer_id,
        private_key=private_key,
    )
    registry = IssuerRegistry((identity,))
    return signer, registry


def test_storage_accepts_only_verified_signed_evidence(tmp_path):
    signer, registry = _signed_system()
    signal = signer.sign(payload={"count": 1}, correlation_id="correlation-1")
    storage = OperationalEvidenceStorage.open(
        control=EvidenceStorageControl(enabled=True),
        database_path=tmp_path / "evidence.sqlite3",
    )

    storage.write_signal(signal, verifier=EvidenceVerifier(registry))
    stored = storage.read_signal(signal.evidence_id)

    assert stored == signal.model_copy(update={"integrity_status": "VERIFIED"})
    storage.close()


def test_storage_rejects_invalid_signature_and_replay(tmp_path):
    signer, registry = _signed_system()
    signal = signer.sign(payload={"count": 1}, correlation_id="correlation-1")
    invalid = signal.model_copy(update={"correlation_id": "tampered"})
    storage = OperationalEvidenceStorage.open(
        control=EvidenceStorageControl(enabled=True),
        database_path=tmp_path / "evidence.sqlite3",
    )
    with pytest.raises(EvidenceIntegrityError):
        storage.write_signal(invalid, verifier=EvidenceVerifier(registry))

    storage.write_signal(signal, verifier=EvidenceVerifier(registry))
    with pytest.raises(EvidenceIntegrityError):
        storage.write_signal(signal, verifier=EvidenceVerifier(registry))
    storage.close()


def test_disabled_storage_creates_nothing(tmp_path):
    path = tmp_path / "evidence.sqlite3"
    storage = OperationalEvidenceStorage.open(
        control=EvidenceStorageControl(enabled=False),
        database_path=path,
    )
    assert storage is None
    assert not path.exists()
