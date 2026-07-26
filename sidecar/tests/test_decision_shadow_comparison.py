from sentinel.decision_shadow_validation import (
    ComponentComparisonStatus,
    DecisionClassification,
    DecisionComparison,
    LegacyDecisionSnapshot,
    V2DecisionSnapshot,
)


def snapshot(model, *, plan="b", policy="c", authorization="e", codes=()):
    return model(
        decision_type="CONTROL",
        decision_status="ALLOW",
        engine_version="1.0",
        intent_hash="a" * 64,
        plan_hash=plan * 64,
        policy_hash=policy * 64,
        discovery_hash="d" * 64,
        authorization_hash=authorization * 64,
        codes=codes,
    )


def test_deep_component_comparison() -> None:
    components, classification = DecisionComparison.compare(
        snapshot(LegacyDecisionSnapshot),
        snapshot(V2DecisionSnapshot, plan="f"),
    )
    assert components.intent is ComponentComparisonStatus.MATCH
    assert components.plan is ComponentComparisonStatus.DIFFERENT
    assert components.policy is ComponentComparisonStatus.MATCH
    assert components.discovery is ComponentComparisonStatus.MATCH
    assert components.authorization is ComponentComparisonStatus.MATCH
    assert classification is DecisionClassification.V2_DIFFERENCE


def test_policy_difference_is_critical() -> None:
    _, classification = DecisionComparison.compare(
        snapshot(LegacyDecisionSnapshot),
        snapshot(V2DecisionSnapshot, policy="f"),
    )
    assert classification is DecisionClassification.CRITICAL_DIVERGENCE


def test_security_improvement_is_classified() -> None:
    _, classification = DecisionComparison.compare(
        snapshot(LegacyDecisionSnapshot),
        snapshot(
            V2DecisionSnapshot,
            authorization="f",
            codes=("SECURITY_IMPROVEMENT",),
        ),
    )
    assert classification is DecisionClassification.SECURITY_IMPROVEMENT


def test_legacy_known_gap_is_classified() -> None:
    _, classification = DecisionComparison.compare(
        snapshot(
            LegacyDecisionSnapshot,
            plan="f",
            codes=("LEGACY_KNOWN_GAP",),
        ),
        snapshot(V2DecisionSnapshot),
    )
    assert classification is DecisionClassification.LEGACY_DIFFERENCE
