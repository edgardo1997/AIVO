from sentinel.runtime_equivalence_validation import (
    EquivalenceClassification,
    EquivalenceMetrics,
    RuntimeEquivalenceReport,
)


def test_metrics_are_aggregate_only() -> None:
    metrics = EquivalenceMetrics()
    metrics.record(
        classification=EquivalenceClassification.EQUIVALENT,
        latency_ms=10,
    )
    metrics.record(
        classification=EquivalenceClassification.FUNCTIONAL_DIFFERENCE,
        latency_ms=30,
    )
    metrics.record(
        classification=EquivalenceClassification.UNKNOWN,
        latency_ms=20,
        error=True,
    )
    snapshot = metrics.snapshot()
    assert snapshot.comparisons == 3
    assert snapshot.matches == 1
    assert snapshot.divergences == 2
    assert snapshot.errors == 1
    assert snapshot.average_latency_ms == 20
    assert snapshot.maximum_latency_ms == 30
    assert not hasattr(metrics, "snapshots")
    assert not hasattr(metrics, "payloads")


def test_report_contains_aggregate_result() -> None:
    metrics = EquivalenceMetrics()
    metrics.record(
        classification=EquivalenceClassification.EQUIVALENT,
        latency_ms=1,
    )
    report = RuntimeEquivalenceReport(
        metrics=metrics.snapshot(),
        risks=(),
        recommendation="CONTINUE_ISOLATED_VALIDATION",
    )
    assert report.human_readable().startswith("SENTINEL RUNTIME EQUIVALENCE VALIDATION REPORT")
    assert "100.00%" in report.human_readable()
