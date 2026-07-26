from sentinel.runtime_trial import (
    RuntimeTrialComparisonStatus,
    RuntimeTrialHealthEvaluator,
    RuntimeTrialHealthStatus,
    RuntimeTrialMetrics,
    RuntimeTrialReport,
)


def test_metrics_are_sanitized_aggregates() -> None:
    metrics = RuntimeTrialMetrics()
    metrics.record(
        succeeded=True,
        comparison=RuntimeTrialComparisonStatus.MATCH,
        latency_ms=10,
        conversions=5,
    )
    metrics.record(
        succeeded=False,
        comparison=RuntimeTrialComparisonStatus.CRITICAL_DIVERGENCE,
        latency_ms=30,
        conversions=4,
    )
    snapshot = metrics.snapshot()
    assert snapshot.scenarios_run == 2
    assert snapshot.successes == 1
    assert snapshot.failures == 1
    assert snapshot.divergences == 1
    assert snapshot.average_latency_ms == 20
    assert snapshot.maximum_latency_ms == 30
    assert snapshot.conversions == 9
    assert not hasattr(metrics, "scenarios")
    assert not hasattr(metrics, "payloads")


def test_health_and_report() -> None:
    metrics = RuntimeTrialMetrics()
    metrics.record(
        succeeded=True,
        comparison=RuntimeTrialComparisonStatus.MATCH,
        latency_ms=5,
        conversions=5,
    )
    snapshot = metrics.snapshot()
    health = RuntimeTrialHealthEvaluator().evaluate(snapshot)
    assert health is RuntimeTrialHealthStatus.HEALTHY
    report = RuntimeTrialReport(
        health=health,
        metrics=snapshot,
        scenarios=("KNOWN_APPLICATION_SIMULATION",),
        risks=(),
    )
    assert report.human_readable().startswith("SENTINEL CONTROLLED V2 RUNTIME TRIAL REPORT")


def test_health_fails_when_isolation_is_lost() -> None:
    metrics = RuntimeTrialMetrics().snapshot()
    assert (
        RuntimeTrialHealthEvaluator().evaluate(
            metrics,
            isolated=False,
        )
        is RuntimeTrialHealthStatus.CRITICAL
    )
