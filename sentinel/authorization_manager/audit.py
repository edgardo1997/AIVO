"""Authorization audit and telemetry event creation."""

import hashlib
from datetime import datetime

from sentinel.contracts import (
    AuditEventV1,
    AuthorizationGrantV1,
    EvidenceIntegrityStatusV1,
    HealthStateV1,
)
from sentinel.operational_telemetry_hub import OperationalEventV1


def authorization_events(
    grant: AuthorizationGrantV1,
    *,
    timestamp: datetime,
) -> tuple[AuditEventV1, OperationalEventV1]:
    suffix = hashlib.sha256(
        (f"{grant.grant_id}:{grant.status.value}:{timestamp.isoformat()}").encode("utf-8")
    ).hexdigest()[:24]
    audit = AuditEventV1(
        event_id=f"authorization-audit:{suffix}",
        event_type="V2_AUTHORIZATION_RECORDED",
        timestamp=timestamp,
        correlation_id=grant.correlation_id,
        evidence_hash=grant.evidence_hash,
        issuer_id=grant.issuer_id,
        result=grant.status.value,
    )
    operational = OperationalEventV1(
        event_id=f"telemetry:authorization:{suffix}",
        correlation_id=grant.correlation_id,
        evidence_hash=grant.evidence_hash,
        issuer_id=grant.issuer_id,
        timestamp=timestamp,
        event_type="V2_AUTHORIZATION_RECORDED",
        health_state=HealthStateV1.OBSERVING,
        decision_state=grant.status.value,
        integrity_status=EvidenceIntegrityStatusV1.VERIFIED,
    )
    return audit, operational
