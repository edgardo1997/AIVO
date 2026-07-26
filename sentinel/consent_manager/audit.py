"""Consent audit and operational event factories."""

import hashlib

from sentinel.contracts import (
    AuditEventV1,
    ConsentDecisionResultV1,
    HealthStateV1,
)
from sentinel.operational_telemetry_hub import OperationalEventV1


def consent_events(
    consent: ConsentDecisionResultV1,
) -> tuple[AuditEventV1, OperationalEventV1]:
    suffix = hashlib.sha256(
        (f"{consent.consent_id}:{consent.decision.value}:{consent.timestamp.isoformat()}").encode("utf-8")
    ).hexdigest()[:24]
    audit = AuditEventV1(
        event_id=f"consent-audit:{suffix}",
        event_type="V2_CONSENT_RECORDED",
        timestamp=consent.timestamp,
        correlation_id=consent.correlation_id,
        evidence_hash=consent.evidence_hash,
        issuer_id=consent.issuer_id,
        result=consent.decision.value,
    )
    operational = OperationalEventV1(
        event_id=f"telemetry:consent:{suffix}",
        correlation_id=consent.correlation_id,
        evidence_hash=consent.evidence_hash,
        issuer_id=consent.issuer_id,
        timestamp=consent.timestamp,
        event_type="V2_CONSENT_RECORDED",
        health_state=HealthStateV1.OBSERVING,
        decision_state=consent.decision.value,
        integrity_status="VERIFIED",
    )
    return audit, operational
