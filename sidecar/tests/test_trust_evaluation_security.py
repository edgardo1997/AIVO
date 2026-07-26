from sentinel.v2_trust_evaluation import (
    ConfidenceState,
    RecommendationState,
    TrustEvaluationMetrics,
    TrustEvaluationReport,
    TrustEvaluationResultV1,
)


def test_result_has_no_authority_or_action_capability() -> None:
    fields = set(TrustEvaluationResultV1.model_fields)
    assert TrustEvaluationResultV1.model_fields["authority"].default is False
    assert TrustEvaluationResultV1.model_fields["execution_requested"].default is False
    assert "action_requested" not in TrustEvaluationResultV1.model_fields
    assert fields.isdisjoint({"tool", "grant", "command", "arguments", "payload", "runtime"})


def test_metrics_are_aggregate_only() -> None:
    metrics = TrustEvaluationMetrics()
    metrics.record(
        confidence=ConfidenceState.LOW_CONFIDENCE,
        recommendation=RecommendationState.BLOCK_MIGRATION,
    )
    metrics.record(
        confidence=ConfidenceState.TRUST_READY_REVIEW,
        recommendation=RecommendationState.REQUEST_REVIEW,
    )
    snapshot = metrics.snapshot()
    assert snapshot.evaluations == 2
    assert snapshot.confidence_changes == 1
    assert snapshot.blocked_recommendations == 1
    assert snapshot.review_requests == 1
    assert not hasattr(metrics, "history")
    assert not hasattr(metrics, "payloads")


def test_report_is_diagnostic_only() -> None:
    result = TrustEvaluationResultV1(
        confidence=ConfidenceState.UNKNOWN,
        score=0,
        positive_factors=(),
        negative_factors=("INSUFFICIENT_HISTORY",),
        recommendation=RecommendationState.NO_RECOMMENDATION,
    )
    report = TrustEvaluationReport(
        result=result,
        risks=("INSUFFICIENT_HISTORY",),
    )
    assert report.human_readable().startswith("SENTINEL V2 TRUST EVALUATION REPORT")
