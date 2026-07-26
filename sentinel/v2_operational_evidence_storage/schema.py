"""Versioned schema and immutable evidence record."""

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from sentinel.contracts._base import require_timezone

from .integrity import canonical_integrity_hash

SCHEMA_VERSION = 2
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS storage_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS operational_evidence (
    event_id_hash TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,
    correlation_hash TEXT NOT NULL,
    result_code TEXT NOT NULL,
    health_state TEXT NOT NULL,
    incident_state TEXT NOT NULL,
    integrity_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS signed_evidence (
    evidence_id TEXT PRIMARY KEY,
    issuer_id TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    signature TEXT NOT NULL,
    integrity_status TEXT NOT NULL,
    UNIQUE(correlation_id, payload_hash, signature)
);
"""

HashValue = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
CodeValue = Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")]


class EvidenceRecordV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id_hash: HashValue
    timestamp: Annotated[datetime, AfterValidator(require_timezone)]
    event_type: CodeValue
    correlation_hash: HashValue
    result_code: CodeValue
    health_state: CodeValue
    incident_state: CodeValue
    integrity_hash: HashValue

    @classmethod
    def create(
        cls,
        *,
        event_id_hash: str,
        timestamp: datetime,
        event_type: str,
        correlation_hash: str,
        result_code: str,
        health_state: str,
        incident_state: str,
    ) -> "EvidenceRecordV1":
        values = {
            "event_id_hash": event_id_hash,
            "timestamp": timestamp,
            "event_type": event_type,
            "correlation_hash": correlation_hash,
            "result_code": result_code,
            "health_state": health_state,
            "incident_state": incident_state,
        }
        integrity_hash = canonical_integrity_hash(_canonical_values(values))
        return cls(**values, integrity_hash=integrity_hash)

    def integrity_valid(self) -> bool:
        values = self.model_dump(exclude={"integrity_hash"})
        return self.integrity_hash == canonical_integrity_hash(_canonical_values(values))


def _canonical_values(values: dict) -> dict:
    return {key: value.isoformat() if isinstance(value, datetime) else value for key, value in values.items()}
