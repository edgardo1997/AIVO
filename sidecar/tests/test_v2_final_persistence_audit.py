from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from sentinel.evidence_integrity import (
    EvidenceSigner,
    EvidenceVerificationStatus,
    EvidenceVerifier,
    IssuerIdentityV1,
    IssuerRegistry,
)
from sentinel.operational_telemetry_hub import OperationalTelemetryStorage
from sentinel.persistent_control_boundary import PersistentControlStorage


def test_persistent_stores_enable_wal_and_foreign_keys(tmp_path):
    stores = (
        PersistentControlStorage(tmp_path / "control.sqlite3"),
        OperationalTelemetryStorage(tmp_path / "telemetry.sqlite3"),
    )
    for storage in stores:
        connection = storage.connection
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        storage.close()


def test_ed25519_provenance_hash_tampering_and_replay_protection():
    private_key = Ed25519PrivateKey.generate()
    identity = IssuerIdentityV1(
        issuer_id="issuer.audit.v1",
        public_key=private_key.public_key().public_bytes_raw(),
        identity_version="1",
    )
    signer = EvidenceSigner(
        issuer_id=identity.issuer_id,
        private_key=private_key,
    )
    verifier = EvidenceVerifier(IssuerRegistry((identity,)))
    payload = {"event_type": "FINAL_AUDIT", "count": 1}
    signal = signer.sign(payload=payload, correlation_id="final-audit-1")

    assert verifier.verify(signal, payload=payload).status is EvidenceVerificationStatus.VERIFIED
    assert verifier.verify(signal, payload=payload).status is EvidenceVerificationStatus.REPLAY_DETECTED
    fresh_verifier = EvidenceVerifier(IssuerRegistry((identity,)))
    assert (
        fresh_verifier.verify(signal, payload={**payload, "count": 2}).status
        is EvidenceVerificationStatus.HASH_MISMATCH
    )
