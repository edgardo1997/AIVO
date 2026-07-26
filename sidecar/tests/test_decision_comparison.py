from sentinel.core.policy import PolicyEffect
from sentinel.shadow import (
    ShadowDecisionComparison,
    ShadowDecisionComparisonStatus,
)


def test_decision_comparison_matches_equivalent_decisions():
    result = ShadowDecisionComparison.compare(
        component="executor.launch",
        legacy_decision=PolicyEffect.REQUIRE_CONFIRM,
        shadow_decision="REQUIRE_CONSENT",
    )
    assert result.status is ShadowDecisionComparisonStatus.MATCH
    assert result.same_decision is True
    assert result.differences == ()


def test_decision_comparison_reports_divergence():
    result = ShadowDecisionComparison.compare(
        component="executor.launch",
        legacy_decision="ALLOW",
        shadow_decision="DENY",
    )
    assert result.status is ShadowDecisionComparisonStatus.DIVERGENCE
    assert result.same_decision is False
    assert result.differences == ("decision_changed:ALLOW->DENY",)


def test_decision_comparison_reports_conversion_error():
    result = ShadowDecisionComparison.compare(
        component="executor.launch",
        legacy_decision="UNKNOWN",
        shadow_decision="ALLOW",
    )
    assert result.status is ShadowDecisionComparisonStatus.ERROR
    assert result.differences


def test_decision_comparison_preserves_missing_information_warning():
    result = ShadowDecisionComparison.compare(
        component="executor.launch",
        legacy_decision="ALLOW",
        shadow_decision="ALLOW",
        missing_information=("identity_context",),
    )
    assert result.status is ShadowDecisionComparisonStatus.MATCH
    assert result.warnings == ("missing_information: identity_context",)
    assert result.differences == ("identity_context",)
