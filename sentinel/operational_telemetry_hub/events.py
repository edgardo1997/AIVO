"""Central immutable operational event and future adapter factories."""

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator, Field

from sentinel.contracts import (
    AuditEventV1,
    DecisionResultV1,
    EvidenceIntegrityStatusV1,
    EvidenceSignalV1,
    HealthStateV1,
)
from sentinel.contracts._base import require_timezone

SafeIdentifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")]
HashValue = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
CodeValue = Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")]
AwareDatetime = Annotated[datetime, AfterValidator(require_timezone)]


class OperationalEventV1(DecisionResultV1):
    event_id: SafeIdentifier
    correlation_id: SafeIdentifier
    evidence_hash: HashValue
    issuer_id: SafeIdentifier
    timestamp: AwareDatetime
    event_type: CodeValue
    health_state: HealthStateV1
    decision_state: CodeValue
    integrity_status: EvidenceIntegrityStatusV1

    def canonical_hash(self) -> str:
        values = self.model_dump(
            mode="json",
            exclude={"authority", "execution_requested"},
        )
        canonical = json.dumps(values, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class OperationalEventFactory:
    """Explicit adapters for already-sanitized central contracts."""

    @staticmethod
    def from_evidence(
        signal: EvidenceSignalV1,
        *,
        event_type: str,
        health_state: HealthStateV1,
        decision_state: str,
    ) -> OperationalEventV1:
        return OperationalEventV1(
            event_id=f"telemetry:{signal.evidence_id}",
            correlation_id=signal.correlation_id,
            evidence_hash=signal.payload_hash,
            issuer_id=signal.issuer_id,
            timestamp=signal.created_at,
            event_type=event_type,
            health_state=health_state,
            decision_state=decision_state,
            integrity_status=signal.integrity_status,
        )

    @staticmethod
    def from_audit(
        event: AuditEventV1,
        *,
        issuer_id: str | None = None,
        health_state: HealthStateV1,
        decision_state: str,
    ) -> OperationalEventV1:
        return OperationalEventV1(
            event_id=f"telemetry:{event.event_id}",
            correlation_id=event.correlation_id,
            evidence_hash=event.evidence_hash,
            issuer_id=issuer_id or event.issuer_id,
            timestamp=event.timestamp,
            event_type=event.event_type.upper(),
            health_state=health_state,
            decision_state=decision_state,
            integrity_status=EvidenceIntegrityStatusV1.UNKNOWN,
        )

    @staticmethod
    def synthetic(
        *,
        correlation_id: str,
        evidence_hash: str,
        issuer_id: str,
        event_type: str,
        health_state: HealthStateV1,
        decision_state: str,
    ) -> OperationalEventV1:
        return OperationalEventV1(
            event_id=f"telemetry:{uuid.uuid4().hex}",
            correlation_id=correlation_id,
            evidence_hash=evidence_hash,
            issuer_id=issuer_id,
            timestamp=datetime.now(UTC),
            event_type=event_type,
            health_state=health_state,
            decision_state=decision_state,
            integrity_status=EvidenceIntegrityStatusV1.UNKNOWN,
        )
