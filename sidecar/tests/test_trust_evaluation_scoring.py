from sentinel.v2_trust_evaluation import (
    ConfidenceState,
    HistoricalEvidenceV1,
    TrustEvaluationControl,
    TrustEvaluator,
)


def history(**updates):
    values = {
        "window_count": 4,
        "total_events": 1000,
        "stable_windows": 4,
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


def evaluate(**updates):
    return TrustEvaluator(control=TrustEvaluationControl(enabled=True)).evaluate(history(**updates))


def test_perfect_score_is_one_hundred() -> None:
    result = evaluate()
    assert result.score == 100
    assert "STABILITY_HIGH" in result.positive_factors
    assert "EVIDENCE_INTEGRITY_HIGH" in result.positive_factors


def test_errors_divergences_incidents_and_rollback_reduce_score() -> None:
    baseline = evaluate()
    degraded = evaluate(
        error_rate=0.1,
        divergence_rate=0.1,
        incident_count=2,
        rollback_count=1,
    )
    assert degraded.score < baseline.score
    assert set(degraded.negative_factors) >= {
        "ERRORS_OBSERVED",
        "DIVERGENCES_OBSERVED",
        "INCIDENTS_OBSERVED",
        "ROLLBACKS_OBSERVED",
    }


def test_high_score_without_enough_windows_is_not_review_ready() -> None:
    result = evaluate(window_count=1, stable_windows=1)
    assert result.confidence is ConfidenceState.HIGH_CONFIDENCE
