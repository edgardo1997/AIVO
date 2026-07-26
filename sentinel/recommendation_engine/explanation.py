"""Complete human-readable recommendation explanation contract."""

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator

from sentinel.contracts import (
    DecisionResultV1,
    EvidenceIntegrityStatusV1,
    HealthStateV1,
    ReadinessStateValueV1,
)
from sentinel.contracts._base import require_timezone
from sentinel.shadow_decision_orchestrator import EquivalenceLevel

from .risk import RiskLevel

AwareDatetime = Annotated[datetime, AfterValidator(require_timezone)]


class RecommendationExplanationV1(DecisionResultV1):
    reason: str
    confidence: float
    risk: RiskLevel
    health: HealthStateV1
    readiness: ReadinessStateValueV1
    equivalence: EquivalenceLevel
    divergence_count: int
    evidence_status: EvidenceIntegrityStatusV1
    signature_status: EvidenceIntegrityStatusV1
    issuer_id: str
    correlation_id: str
    timestamp: AwareDatetime


def explanation_reason(
    *,
    risk: RiskLevel,
    equivalence: EquivalenceLevel,
    integrity: EvidenceIntegrityStatusV1,
) -> str:
    if integrity is not EvidenceIntegrityStatusV1.VERIFIED:
        return "Evidence is not verified; continue no activation review."
    if risk in {RiskLevel.CRITICAL, RiskLevel.HIGH}:
        return f"Risk is {risk.value} and equivalence is {equivalence.value}; recommendation is blocked."
    if risk is RiskLevel.MEDIUM:
        return "Evidence is incomplete or partially equivalent; continue passive observation."
    return "Evidence is verified, health is acceptable, and decisions are equivalent; human review may proceed."
