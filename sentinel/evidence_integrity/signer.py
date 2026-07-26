"""Ed25519 evidence signing over deterministic canonical content."""

import base64
import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Mapping

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from sentinel.contracts import EvidenceIntegrityStatusV1, EvidenceSignalV1

_FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "prompt",
        "command",
        "path",
        "secret",
        "token",
        "arguments",
        "tool_arguments",
    }
)


def canonical_payload_hash(payload: Mapping[str, object]) -> str:
    _reject_sensitive_keys(payload)
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def canonical_signal_content(
    *,
    evidence_id: str,
    issuer_id: str,
    schema_version: str,
    created_at: datetime,
    correlation_id: str,
    payload_hash: str,
) -> bytes:
    values = {
        "correlation_id": correlation_id,
        "created_at": created_at.isoformat(),
        "evidence_id": evidence_id,
        "issuer_id": issuer_id,
        "payload_hash": payload_hash,
        "schema_version": schema_version,
    }
    return json.dumps(
        values,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


class EvidenceSigner:
    def __init__(
        self,
        *,
        issuer_id: str,
        private_key: Ed25519PrivateKey,
    ) -> None:
        self.issuer_id = issuer_id
        self._private_key = private_key

    def sign(
        self,
        *,
        payload: Mapping[str, object],
        correlation_id: str,
        created_at: datetime | None = None,
        evidence_id: str | None = None,
    ) -> EvidenceSignalV1:
        timestamp = created_at or datetime.now(UTC)
        identifier = evidence_id or f"evidence:{uuid.uuid4().hex}"
        payload_hash = canonical_payload_hash(payload)
        content = canonical_signal_content(
            evidence_id=identifier,
            issuer_id=self.issuer_id,
            schema_version="1.0",
            created_at=timestamp,
            correlation_id=correlation_id,
            payload_hash=payload_hash,
        )
        signature = base64.urlsafe_b64encode(self._private_key.sign(content)).decode("ascii")
        return EvidenceSignalV1(
            evidence_id=identifier,
            issuer_id=self.issuer_id,
            created_at=timestamp,
            correlation_id=correlation_id,
            payload_hash=payload_hash,
            signature=signature,
            integrity_status=EvidenceIntegrityStatusV1.SIGNED,
        )


def _reject_sensitive_keys(value: object) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if str(key).lower() in _FORBIDDEN_PAYLOAD_KEYS:
                raise ValueError(f"sensitive payload field rejected: {key}")
            _reject_sensitive_keys(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _reject_sensitive_keys(nested)
