"""Authenticity, provenance and replay verification for signed evidence."""

import base64
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from sentinel.contracts import EvidenceSignalV1

from .identity import IssuerRegistry
from .signer import canonical_payload_hash, canonical_signal_content


class EvidenceVerificationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    INVALID_SIGNATURE = "INVALID_SIGNATURE"
    UNKNOWN_ISSUER = "UNKNOWN_ISSUER"
    HASH_MISMATCH = "HASH_MISMATCH"
    EXPIRED = "EXPIRED"
    REPLAY_DETECTED = "REPLAY_DETECTED"


@dataclass(frozen=True)
class EvidenceVerificationResult:
    status: EvidenceVerificationStatus
    evidence_id: str
    issuer_id: str
    authority: bool = False
    execution_requested: bool = False


class EvidenceVerifier:
    def __init__(
        self,
        registry: IssuerRegistry,
        *,
        maximum_age: timedelta = timedelta(hours=24),
    ) -> None:
        self.registry = registry
        self.maximum_age = maximum_age
        self._seen_evidence_ids: set[str] = set()

    def verify(
        self,
        signal: EvidenceSignalV1,
        *,
        payload: Mapping[str, object] | None = None,
        now: datetime | None = None,
        detect_replay: bool = True,
    ) -> EvidenceVerificationResult:
        identity = self.registry.get(signal.issuer_id)
        if identity is None:
            return self._result(EvidenceVerificationStatus.UNKNOWN_ISSUER, signal)
        observed_at = now or datetime.now(UTC)
        if signal.created_at > observed_at + timedelta(minutes=5) or observed_at - signal.created_at > self.maximum_age:
            return self._result(EvidenceVerificationStatus.EXPIRED, signal)
        if payload is not None and canonical_payload_hash(payload) != signal.payload_hash:
            return self._result(EvidenceVerificationStatus.HASH_MISMATCH, signal)
        content = canonical_signal_content(
            evidence_id=signal.evidence_id,
            issuer_id=signal.issuer_id,
            schema_version=signal.schema_version,
            created_at=signal.created_at,
            correlation_id=signal.correlation_id,
            payload_hash=signal.payload_hash,
        )
        try:
            signature = base64.urlsafe_b64decode(signal.signature.encode("ascii"))
            Ed25519PublicKey.from_public_bytes(identity.public_key).verify(
                signature,
                content,
            )
        except (InvalidSignature, ValueError):
            return self._result(EvidenceVerificationStatus.INVALID_SIGNATURE, signal)
        if detect_replay and signal.evidence_id in self._seen_evidence_ids:
            return self._result(EvidenceVerificationStatus.REPLAY_DETECTED, signal)
        if detect_replay:
            self._seen_evidence_ids.add(signal.evidence_id)
        return self._result(EvidenceVerificationStatus.VERIFIED, signal)

    @staticmethod
    def _result(
        status: EvidenceVerificationStatus,
        signal: EvidenceSignalV1,
    ) -> EvidenceVerificationResult:
        return EvidenceVerificationResult(
            status=status,
            evidence_id=signal.evidence_id,
            issuer_id=signal.issuer_id,
        )
