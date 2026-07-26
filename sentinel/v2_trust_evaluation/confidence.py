"""Confidence classification; readiness is review-only."""

from enum import Enum

from .criteria import TrustCriteriaV1
from .history import HistoricalEvidenceV1


class ConfidenceState(str, Enum):
    UNKNOWN = "UNKNOWN"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    MODERATE_CONFIDENCE = "MODERATE_CONFIDENCE"
    HIGH_CONFIDENCE = "HIGH_CONFIDENCE"
    TRUST_READY_REVIEW = "TRUST_READY_REVIEW"


class ConfidenceClassifier:
    def classify(
        self,
        score: float,
        evidence: HistoricalEvidenceV1,
        criteria: TrustCriteriaV1,
    ) -> ConfidenceState:
        if evidence.window_count == 0:
            return ConfidenceState.UNKNOWN
        if score < 40:
            return ConfidenceState.LOW_CONFIDENCE
        if score < 65:
            return ConfidenceState.MODERATE_CONFIDENCE
        ready = (
            score >= criteria.trust_ready_score
            and evidence.window_count >= criteria.minimum_windows_for_review
            and evidence.integrity_rate >= criteria.minimum_integrity_rate
            and evidence.error_rate <= criteria.maximum_error_rate
            and evidence.critical_divergences <= criteria.maximum_critical_divergences
        )
        if ready:
            return ConfidenceState.TRUST_READY_REVIEW
        return ConfidenceState.HIGH_CONFIDENCE
