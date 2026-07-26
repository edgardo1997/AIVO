from sentinel.activation_gateway import (
    ActivationGatewayMetrics,
    ActivationGatewayReport,
    SelectedAuthority,
)


def test_metrics_are_aggregate_only() -> None:
    metrics = ActivationGatewayMetrics()
    metrics.record_selection(SelectedAuthority.LEGACY_ONLY)
    metrics.record_selection(SelectedAuthority.V2_ELIGIBLE_CANARY)
    metrics.record_selection(SelectedAuthority.BLOCKED)
    metrics.record_fallback()
    metrics.record_error()
    snapshot = metrics.snapshot()

    assert snapshot.total_evaluations == 3
    assert snapshot.legacy_selected == 1
    assert snapshot.v2_candidate_selected == 1
    assert snapshot.blocked == 1
    assert snapshot.fallbacks == 1
    assert snapshot.errors == 1
    assert not hasattr(metrics, "requests")
    assert not hasattr(metrics, "payloads")


def test_report_is_aggregate() -> None:
    report = ActivationGatewayReport(
        metrics=ActivationGatewayMetrics().snapshot(),
        risks=(),
        recommendation="KEEP_LEGACY_AUTHORITY",
    )
    assert report.human_readable().startswith("SENTINEL V2 ACTIVATION GATEWAY REPORT")
