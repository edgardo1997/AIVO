from datetime import datetime, timedelta, timezone

from sentinel.decision_long_term_evaluation import (
    DecisionLongTermHealthEvaluator,
    DecisionLongTermHealthStatus,
    DecisionLongTermMetrics,
    DecisionLongTermReport,
    EvaluationWindowV1,
    TrendStatus,
)
from sentinel.decision_shadow_validation import DecisionClassification


def test_metrics_calculate_rates_and_latency() -> None:
    metrics = DecisionLongTermMetrics()
    metrics.record(
        classification=DecisionClassification.EXPECTED_MATCH,
        latency_ms=10,
    )
    metrics.record(
        classification=DecisionClassification.CRITICAL_DIVERGENCE,
        latency_ms=30,
        error=True,
    )
    result = metrics.snapshot()
    assert result.total_decisions == 2
    assert result.match_rate == 0.5
    assert result.divergence_rate == 0.5
    assert result.error_rate == 0.5
    assert result.critical_divergences == 1
    assert result.average_latency_ms == 20
    assert result.maximum_latency_ms == 30
    assert not hasattr(metrics, "decisions")


def test_health_considers_volume_errors_critical_and_loss() -> None:
    metrics = DecisionLongTermMetrics()
    low_volume = metrics.snapshot()
    evaluator = DecisionLongTermHealthEvaluator()
    assert (
        evaluator.evaluate(
            low_volume,
            trend=TrendStatus.STABLE,
        )
        is DecisionLongTermHealthStatus.WARNING
    )
    metrics.record_loss(11)
    assert (
        evaluator.evaluate(
            metrics.snapshot(),
            trend=TrendStatus.STABLE,
        )
        is DecisionLongTermHealthStatus.CRITICAL
    )


def test_human_report() -> None:
    started = datetime(2026, 7, 24, tzinfo=timezone.utc)
    window = EvaluationWindowV1.create(started).model_copy(
        update={
            "state": "COMPLETED",
            "ended_at": started + timedelta(hours=2),
        }
    )
    report = DecisionLongTermReport(
        window=window,
        metrics=DecisionLongTermMetrics().snapshot(),
        trend=TrendStatus.STABLE,
        health=DecisionLongTermHealthStatus.WARNING,
        risks=("INSUFFICIENT_VOLUME",),
        recommendation="continue_observation",
    )
    assert report.human_readable().startswith("SENTINEL DECISION SHADOW LONG TERM REPORT")
