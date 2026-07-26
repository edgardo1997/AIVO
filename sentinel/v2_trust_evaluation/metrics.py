"""Aggregate-only trust evaluation metrics."""

from dataclasses import dataclass
from threading import RLock

from .confidence import ConfidenceState
from .recommendation import RecommendationState


@dataclass(frozen=True)
class TrustEvaluationMetricsSnapshot:
    evaluations: int
    confidence_changes: int
    blocked_recommendations: int
    review_requests: int


class TrustEvaluationMetrics:
    def __init__(self) -> None:
        self._lock = RLock()
        self._evaluations = 0
        self._changes = 0
        self._blocked = 0
        self._reviews = 0
        self._last_confidence: ConfidenceState | None = None

    def record(
        self,
        *,
        confidence: ConfidenceState,
        recommendation: RecommendationState,
    ) -> None:
        with self._lock:
            self._evaluations += 1
            self._changes += int(self._last_confidence is not None and confidence is not self._last_confidence)
            self._last_confidence = confidence
            self._blocked += int(recommendation is RecommendationState.BLOCK_MIGRATION)
            self._reviews += int(recommendation is RecommendationState.REQUEST_REVIEW)

    def snapshot(self) -> TrustEvaluationMetricsSnapshot:
        with self._lock:
            return TrustEvaluationMetricsSnapshot(
                evaluations=self._evaluations,
                confidence_changes=self._changes,
                blocked_recommendations=self._blocked,
                review_requests=self._reviews,
            )
