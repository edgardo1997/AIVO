from datetime import datetime, timezone

from sentinel.decision_long_term_evaluation import (
    DecisionAggregateSnapshot,
    DecisionTrendAnalyzer,
    EvaluationWindowV1,
    TrendStatus,
)


def aggregate(matches, total=100, critical=0, errors=0):
    return DecisionAggregateSnapshot(
        total_decisions=total,
        matches=matches,
        divergences=total - matches,
        security_improvements=0,
        critical_divergences=critical,
        errors=errors,
        average_latency_ms=5,
        maximum_latency_ms=10,
        lost_records=0,
    )


def test_window_identity_is_deterministic_and_timezone_aware() -> None:
    started = datetime(2026, 7, 24, tzinfo=timezone.utc)
    one = EvaluationWindowV1.create(started)
    two = EvaluationWindowV1.create(started)
    assert one.evaluation_id == two.evaluation_id
    assert one.started_at.utcoffset() is not None
    assert one.authority is False


def test_trend_improving_and_degrading() -> None:
    analyzer = DecisionTrendAnalyzer()
    assert analyzer.analyze((aggregate(70), aggregate(80), aggregate(90))) is TrendStatus.IMPROVING
    assert analyzer.analyze((aggregate(95), aggregate(80), aggregate(60))) is TrendStatus.DEGRADING


def test_trend_repeated_critical_divergence_is_unstable() -> None:
    assert (
        DecisionTrendAnalyzer().analyze((aggregate(99, critical=1), aggregate(99, critical=1))) is TrendStatus.UNSTABLE
    )
