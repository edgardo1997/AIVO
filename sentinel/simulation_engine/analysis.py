"""Deterministic confidence analysis over existing contract results."""

from sentinel.contracts import (
    EvidenceIntegrityStatusV1,
    ReadinessResultV1,
)
from sentinel.recommendation_engine import RecommendationResultV1
from sentinel.shadow_decision_orchestrator.orchestrator import (
    ShadowDecisionResultV1,
)
from sentinel.v2_trust_evaluation import TrustEvaluationResultV1


def simulation_confidence(
    *,
    recommendation: RecommendationResultV1,
    trust: TrustEvaluationResultV1,
    readiness: ReadinessResultV1,
    shadow: ShadowDecisionResultV1,
    integrity: EvidenceIntegrityStatusV1,
) -> float:
    if integrity is EvidenceIntegrityStatusV1.INVALID:
        return 0.0
    value = min(
        recommendation.evaluation.confidence,
        trust.score,
        readiness.confidence,
        shadow.comparison.confidence,
    )
    if integrity is not EvidenceIntegrityStatusV1.VERIFIED:
        value = min(value, 25.0)
    return round(value, 2)
