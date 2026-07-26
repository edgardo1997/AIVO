"""Reproducible confidence derived from existing contract confidence."""

from sentinel.contracts import (
    EvidenceIntegrityStatusV1,
    ReadinessResultV1,
    SimulationResultV1,
)
from sentinel.recommendation_engine import RecommendationResultV1
from sentinel.v2_trust_evaluation import TrustEvaluationResultV1


def policy_confidence(
    *,
    simulation: SimulationResultV1,
    recommendation: RecommendationResultV1,
    trust: TrustEvaluationResultV1,
    readiness: ReadinessResultV1,
    integrity: EvidenceIntegrityStatusV1,
) -> float:
    if integrity is EvidenceIntegrityStatusV1.INVALID:
        return 0.0
    value = min(
        simulation.confidence,
        recommendation.evaluation.confidence,
        trust.score,
        readiness.confidence,
    )
    if integrity is not EvidenceIntegrityStatusV1.VERIFIED:
        value = min(value, 25.0)
    return round(value, 2)
