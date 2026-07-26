from sentinel.shadow import (
    ShadowDecisionComparison,
    ShadowDecisionMetrics,
)


def test_shadow_decision_metrics_record_each_outcome():
    metrics = ShadowDecisionMetrics()
    metrics.record_match()
    metrics.record_divergence()
    metrics.record_error()
    metrics.record_error(missing_contract=True)

    assert metrics.total_comparisons == 4
    assert metrics.matches == 1
    assert metrics.divergences == 1
    assert metrics.conversion_errors == 2
    assert metrics.missing_contracts == 1


def test_shadow_decision_metrics_can_record_comparison():
    metrics = ShadowDecisionMetrics()
    metrics.record(
        ShadowDecisionComparison.compare(
            component="policy",
            legacy_decision="ALLOW",
            shadow_decision="ALLOW",
        )
    )
    metrics.record(
        ShadowDecisionComparison.compare(
            component="policy",
            legacy_decision="ALLOW",
            shadow_decision="DENY",
        )
    )
    assert metrics.total_comparisons == 2
    assert metrics.matches == 1
    assert metrics.divergences == 1


def test_shadow_decision_metrics_are_isolated():
    first = ShadowDecisionMetrics()
    second = ShadowDecisionMetrics()
    first.record_match()
    assert second.total_comparisons == 0
