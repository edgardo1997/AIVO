"""Aggregate recommendation counters."""

from dataclasses import dataclass

from sentinel.contracts import DecisionResultV1

from .recommendation import RecommendationValue


class RecommendationMetricSnapshotV1(DecisionResultV1):
    evaluations: int
    review_recommendations: int
    blocked_recommendations: int
    observation_recommendations: int


@dataclass
class RecommendationMetrics:
    evaluations: int = 0
    review_recommendations: int = 0
    blocked_recommendations: int = 0
    observation_recommendations: int = 0

    def record(self, recommendation: RecommendationValue) -> None:
        self.evaluations += 1
        self.review_recommendations += int(
            recommendation
            in {
                RecommendationValue.REQUEST_REVIEW,
                RecommendationValue.SAFE_TO_REVIEW,
                RecommendationValue.HIGH_CONFIDENCE_REVIEW,
            }
        )
        self.blocked_recommendations += int(recommendation is RecommendationValue.BLOCK_RECOMMENDATION)
        self.observation_recommendations += int(recommendation is RecommendationValue.CONTINUE_OBSERVATION)

    def snapshot(self) -> RecommendationMetricSnapshotV1:
        return RecommendationMetricSnapshotV1(**vars(self))
