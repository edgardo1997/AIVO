"""Strict non-operational recommendation vocabulary."""

from enum import Enum

from sentinel.contracts import (
    EvidenceIntegrityStatusV1,
    ReadinessStateValueV1,
)
from sentinel.shadow_decision_orchestrator import EquivalenceLevel
from sentinel.v2_trust_evaluation import ConfidenceState

from .risk import RiskLevel


class RecommendationValue(str, Enum):
    NO_RECOMMENDATION = "NO_RECOMMENDATION"
    CONTINUE_OBSERVATION = "CONTINUE_OBSERVATION"
    REQUEST_REVIEW = "REQUEST_REVIEW"
    SAFE_TO_REVIEW = "SAFE_TO_REVIEW"
    HIGH_CONFIDENCE_REVIEW = "HIGH_CONFIDENCE_REVIEW"
    BLOCK_RECOMMENDATION = "BLOCK_RECOMMENDATION"


def select_recommendation(
    *,
    risk: RiskLevel,
    confidence: float,
    trust: ConfidenceState,
    readiness: ReadinessStateValueV1,
    equivalence: EquivalenceLevel,
    integrity: EvidenceIntegrityStatusV1,
) -> RecommendationValue:
    if risk in {RiskLevel.CRITICAL, RiskLevel.HIGH}:
        return RecommendationValue.BLOCK_RECOMMENDATION
    if risk is RiskLevel.MEDIUM:
        return RecommendationValue.CONTINUE_OBSERVATION
    if (
        confidence >= 90
        and trust is ConfidenceState.TRUST_READY_REVIEW
        and readiness is ReadinessStateValueV1.HIGH_CONFIDENCE_REVIEW
    ):
        return RecommendationValue.HIGH_CONFIDENCE_REVIEW
    if confidence >= 80 and equivalence is EquivalenceLevel.MATCH and integrity is EvidenceIntegrityStatusV1.VERIFIED:
        return RecommendationValue.SAFE_TO_REVIEW
    if readiness is ReadinessStateValueV1.READY_FOR_HUMAN_REVIEW:
        return RecommendationValue.REQUEST_REVIEW
    return RecommendationValue.NO_RECOMMENDATION
