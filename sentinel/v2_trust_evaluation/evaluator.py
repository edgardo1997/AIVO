"""Non-authoritative trust evaluator over aggregate history."""

from sentinel.contracts import DecisionResultV1

from .confidence import ConfidenceClassifier, ConfidenceState
from .control import TrustEvaluationControl
from .criteria import TrustCriteriaV1
from .history import HistoricalEvidenceV1, HistorySummary
from .metrics import TrustEvaluationMetrics
from .recommendation import (
    RecommendationEngine,
    RecommendationState,
)
from .scoring import TrustScoringEngine


class TrustEvaluationResultV1(DecisionResultV1):
    confidence: ConfidenceState
    score: float
    positive_factors: tuple[str, ...]
    negative_factors: tuple[str, ...]
    recommendation: RecommendationState


class TrustEvaluator:
    def __init__(
        self,
        *,
        control: TrustEvaluationControl,
        criteria: TrustCriteriaV1 | None = None,
        metrics: TrustEvaluationMetrics | None = None,
    ) -> None:
        self.control = control
        self.criteria = criteria or TrustCriteriaV1()
        self.metrics = metrics or TrustEvaluationMetrics()
        self._history = HistorySummary()
        self._scoring = TrustScoringEngine()
        self._confidence = ConfidenceClassifier()
        self._recommendation = RecommendationEngine()

    def evaluate(
        self,
        evidence: HistoricalEvidenceV1,
    ) -> TrustEvaluationResultV1 | None:
        if not self.control.enabled:
            return None
        history = self._history.summarize(evidence)
        score = self._scoring.calculate(history)
        confidence = self._confidence.classify(
            score.value,
            history,
            self.criteria,
        )
        recommendation = self._recommendation.recommend(confidence)
        self.metrics.record(
            confidence=confidence,
            recommendation=recommendation.recommendation,
        )
        return TrustEvaluationResultV1(
            confidence=confidence,
            score=score.value,
            positive_factors=score.positive_factors,
            negative_factors=score.negative_factors,
            recommendation=recommendation.recommendation,
        )
