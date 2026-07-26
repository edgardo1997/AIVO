from sentinel.decision_shadow_validation import (
    DecisionClassification,
    DecisionShadowMetrics,
    DecisionShadowReport,
)


def test_metrics_are_aggregate_only() -> None:
    metrics = DecisionShadowMetrics()
    metrics.record(
        classification=DecisionClassification.EXPECTED_MATCH,
        latency_ms=10,
    )
    metrics.record(
        classification=DecisionClassification.SECURITY_IMPROVEMENT,
        latency_ms=30,
    )
    metrics.record(
        classification=DecisionClassification.CRITICAL_DIVERGENCE,
        latency_ms=20,
        error=True,
    )
    snapshot = metrics.snapshot()
    assert snapshot.decisions_evaluated == 3
    assert snapshot.matches == 1
    assert snapshot.divergences == 2
    assert snapshot.security_improvements == 1
    assert snapshot.errors == 1
    assert snapshot.average_latency_ms == 20
    assert snapshot.maximum_latency_ms == 30
    assert not hasattr(metrics, "decisions")
    assert not hasattr(metrics, "payloads")


def test_human_report() -> None:
    metrics = DecisionShadowMetrics()
    metrics.record(
        classification=DecisionClassification.EXPECTED_MATCH,
        latency_ms=1,
    )
    report = DecisionShadowReport(
        metrics=metrics.snapshot(),
        critical_divergences=0,
        risks=(),
        recommendation="continue_shadow_validation",
    )
    rendered = report.human_readable()
    assert rendered.startswith("SENTINEL V2 DECISION SHADOW VALIDATION REPORT")
    assert "100.00%" in rendered
