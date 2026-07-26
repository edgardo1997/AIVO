"""Contract-only deterministic comparison."""

from datetime import datetime
from typing import Protocol

from sentinel.contracts import DecisionResultV1, HealthStateV1

from .divergence import CRITICAL_CODES, DivergenceSeverity
from .equivalence import EquivalenceLevel


class SnapshotContract(Protocol):
    decision: DecisionResultV1
    evidence: object
    readiness: object
    health: object
    audit_event: object
    operational_event: object


class ShadowComparisonV1(DecisionResultV1):
    classification: EquivalenceLevel
    confidence: float
    severity: DivergenceSeverity
    reasons: tuple[str, ...]
    timestamp: datetime
    correlation_id: str
    issuer_id: str
    evidence_hash: str


def compare_contracts(
    legacy: SnapshotContract,
    v2: SnapshotContract,
) -> ShadowComparisonV1:
    reasons: list[str] = []
    if legacy.evidence.correlation_id != v2.evidence.correlation_id:
        reasons.append("CORRELATION_MISMATCH")
    if legacy.evidence.payload_hash != v2.evidence.payload_hash:
        reasons.append("EVIDENCE_HASH_MISMATCH")
    if legacy.evidence.issuer_id != v2.evidence.issuer_id:
        reasons.append("ISSUER_MISMATCH")
    if legacy.health.state is HealthStateV1.CRITICAL or v2.health.state is HealthStateV1.CRITICAL:
        reasons.append("CRITICAL_HEALTH")

    if _logical_dump(legacy.decision) != _logical_dump(v2.decision):
        reasons.append("DECISION_MISMATCH")
    if legacy.readiness.status != v2.readiness.status:
        reasons.append("READINESS_MISMATCH")
    if legacy.health.state != v2.health.state:
        reasons.append("HEALTH_MISMATCH")
    if legacy.evidence.integrity_status != v2.evidence.integrity_status:
        reasons.append("INTEGRITY_MISMATCH")
    if _audit_dump(legacy.audit_event) != _audit_dump(v2.audit_event):
        reasons.append("AUDIT_MISMATCH")
    if _operational_dump(legacy.operational_event) != _operational_dump(v2.operational_event):
        reasons.append("OPERATIONAL_MISMATCH")

    unique_reasons = tuple(dict.fromkeys(reasons))
    if CRITICAL_CODES.intersection(unique_reasons):
        classification = EquivalenceLevel.CRITICAL_DIVERGENCE
        severity = DivergenceSeverity.CRITICAL
        confidence = 0.0
    elif {"DECISION_MISMATCH", "READINESS_MISMATCH"}.intersection(unique_reasons):
        classification = EquivalenceLevel.DIVERGENCE
        severity = DivergenceSeverity.HIGH
        confidence = 40.0
    elif unique_reasons:
        classification = EquivalenceLevel.PARTIAL_MATCH
        severity = DivergenceSeverity.LOW
        confidence = 75.0
    else:
        classification = EquivalenceLevel.MATCH
        severity = DivergenceSeverity.NONE
        confidence = 100.0

    return ShadowComparisonV1(
        classification=classification,
        confidence=confidence,
        severity=severity,
        reasons=unique_reasons or ("LOGICAL_EQUIVALENCE",),
        timestamp=v2.evidence.created_at,
        correlation_id=v2.evidence.correlation_id,
        issuer_id=v2.evidence.issuer_id,
        evidence_hash=v2.evidence.payload_hash,
    )


def _logical_dump(value: object) -> dict[str, object]:
    return value.model_dump(
        mode="json",
        exclude={
            "authority",
            "execution_requested",
            "correlation_id",
            "evidence_hash",
            "issuer_id",
            "timestamp",
        },
    )


def _audit_dump(value: object) -> tuple[str, str]:
    return value.event_type, value.result


def _operational_dump(value: object) -> tuple[object, ...]:
    return (
        value.event_type,
        value.health_state,
        value.decision_state,
        value.integrity_status,
    )
