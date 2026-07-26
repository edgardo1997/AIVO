from sentinel.v2_trust_evaluation import (
    V2_TRUST_EVALUATION_ENABLED,
    ConfidenceState,
    HistoricalEvidenceV1,
    RecommendationState,
    TrustEvaluationControl,
    TrustEvaluator,
)


def evidence(**updates):
    values = {
        "window_count": 5,
        "total_events": 10000,
        "stable_windows": 5,
        "equivalence_rate": 1,
        "integrity_rate": 1,
        "healthy_window_rate": 1,
        "error_rate": 0,
        "divergence_rate": 0,
        "critical_divergences": 0,
        "incident_count": 0,
        "rollback_count": 0,
    }
    values.update(updates)
    return HistoricalEvidenceV1(**values)


def test_disabled_by_default_does_not_evaluate() -> None:
    assert V2_TRUST_EVALUATION_ENABLED is False
    evaluator = TrustEvaluator(control=TrustEvaluationControl(environ={}))
    assert evaluator.evaluate(evidence()) is None
    assert evaluator.metrics.snapshot().evaluations == 0


def test_sufficient_evidence_is_ready_for_human_review_only() -> None:
    result = TrustEvaluator(control=TrustEvaluationControl(enabled=True)).evaluate(evidence())
    assert result.confidence is ConfidenceState.TRUST_READY_REVIEW
    assert result.recommendation is RecommendationState.REQUEST_REVIEW
    assert result.authority is False
    assert result.execution_requested is False


def test_unknown_history_produces_no_recommendation() -> None:
    result = TrustEvaluator(control=TrustEvaluationControl(enabled=True)).evaluate(
        evidence(
            window_count=0,
            total_events=0,
            stable_windows=0,
        )
    )
    assert result.confidence is ConfidenceState.UNKNOWN
    assert result.recommendation is RecommendationState.NO_RECOMMENDATION


def test_low_confidence_blocks_migration_recommendation_only() -> None:
    result = TrustEvaluator(control=TrustEvaluationControl(enabled=True)).evaluate(
        evidence(
            stable_windows=0,
            equivalence_rate=0,
            integrity_rate=0,
            healthy_window_rate=0,
            error_rate=0.5,
            divergence_rate=0.5,
            critical_divergences=2,
            incident_count=5,
            rollback_count=2,
        )
    )
    assert result.confidence is ConfidenceState.LOW_CONFIDENCE
    assert result.recommendation is RecommendationState.BLOCK_MIGRATION
    assert result.execution_requested is False
