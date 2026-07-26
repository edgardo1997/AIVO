"""Risk classification derived only from central contract states."""

from enum import Enum

from sentinel.contracts import (
    EvidenceIntegrityStatusV1,
    HealthStateV1,
    ReadinessStateValueV1,
)
from sentinel.shadow_decision_orchestrator import EquivalenceLevel
from sentinel.v2_trust_evaluation import ConfidenceState


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


def classify_risk(
    *,
    trust: ConfidenceState,
    health: HealthStateV1,
    readiness: ReadinessStateValueV1,
    equivalence: EquivalenceLevel,
    integrity: EvidenceIntegrityStatusV1,
) -> RiskLevel:
    if (
        integrity is EvidenceIntegrityStatusV1.INVALID
        or health is HealthStateV1.CRITICAL
        or readiness is ReadinessStateValueV1.BLOCKED
        or equivalence is EquivalenceLevel.CRITICAL_DIVERGENCE
    ):
        return RiskLevel.CRITICAL
    if (
        health is HealthStateV1.DEGRADED
        or readiness is ReadinessStateValueV1.NOT_APPROVED
        or equivalence is EquivalenceLevel.DIVERGENCE
        or trust is ConfidenceState.LOW_CONFIDENCE
    ):
        return RiskLevel.HIGH
    if (
        health is HealthStateV1.WARNING
        or readiness is ReadinessStateValueV1.INSUFFICIENT_EVIDENCE
        or equivalence is EquivalenceLevel.PARTIAL_MATCH
        or trust in {ConfidenceState.UNKNOWN, ConfidenceState.MODERATE_CONFIDENCE}
        or integrity is EvidenceIntegrityStatusV1.UNKNOWN
    ):
        return RiskLevel.MEDIUM
    return RiskLevel.LOW
