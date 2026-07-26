"""Recommendation vocabulary with explicit non-authority."""

from enum import Enum
from sentinel.contracts import DecisionResultV1

from .confidence import ConfidenceState


class RecommendationState(str, Enum):
    NO_RECOMMENDATION = "NO_RECOMMENDATION"
    CONTINUE_OBSERVATION = "CONTINUE_OBSERVATION"
    EXTEND_CANARY = "EXTEND_CANARY"
    REQUEST_REVIEW = "REQUEST_REVIEW"
    BLOCK_MIGRATION = "BLOCK_MIGRATION"


class TrustRecommendationV1(DecisionResultV1):
    recommendation: RecommendationState


class RecommendationEngine:
    def recommend(
        self,
        confidence: ConfidenceState,
    ) -> TrustRecommendationV1:
        recommendation = {
            ConfidenceState.UNKNOWN: RecommendationState.NO_RECOMMENDATION,
            ConfidenceState.LOW_CONFIDENCE: RecommendationState.BLOCK_MIGRATION,
            ConfidenceState.MODERATE_CONFIDENCE: (RecommendationState.CONTINUE_OBSERVATION),
            ConfidenceState.HIGH_CONFIDENCE: RecommendationState.EXTEND_CANARY,
            ConfidenceState.TRUST_READY_REVIEW: (RecommendationState.REQUEST_REVIEW),
        }[confidence]
        return TrustRecommendationV1(recommendation=recommendation)
