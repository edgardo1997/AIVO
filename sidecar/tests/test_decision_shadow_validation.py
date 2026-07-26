from sentinel.decision_shadow_validation import (
    DECISION_SHADOW_VALIDATION_ENABLED,
    DecisionClassification,
    DecisionShadowValidationControl,
    DecisionShadowValidationEngine,
    LegacyDecisionSnapshot,
    V2DecisionSnapshot,
)


def snapshot(model, *, policy="c", authorization="e", codes=()):
    return model(
        decision_type="APPLICATION_CONTROL",
        decision_status="ALLOW",
        engine_version="2.0",
        intent_hash="a" * 64,
        plan_hash="b" * 64,
        policy_hash=policy * 64,
        discovery_hash="d" * 64,
        authorization_hash=authorization * 64,
        codes=codes,
    )


def test_disabled_by_default_does_not_compare_or_measure() -> None:
    assert DECISION_SHADOW_VALIDATION_ENABLED is False
    engine = DecisionShadowValidationEngine(control=DecisionShadowValidationControl(environ={}))
    assert (
        engine.validate(
            snapshot(LegacyDecisionSnapshot),
            snapshot(V2DecisionSnapshot),
        )
        is None
    )
    assert engine.metrics.snapshot().decisions_evaluated == 0


def test_matching_decisions_produce_non_authoritative_result() -> None:
    engine = DecisionShadowValidationEngine(control=DecisionShadowValidationControl(enabled=True))
    result = engine.validate(
        snapshot(LegacyDecisionSnapshot),
        snapshot(V2DecisionSnapshot),
    )
    assert result is not None
    assert result.classification is DecisionClassification.EXPECTED_MATCH
    assert result.authority is False
    assert result.timestamp.utcoffset() is not None
    assert len(result.legacy_hash) == 64
    assert len(result.v2_hash) == 64


def test_comparison_errors_are_isolated() -> None:
    class FailingComparison:
        @staticmethod
        def compare(legacy, v2):
            raise RuntimeError("secret")

    engine = DecisionShadowValidationEngine(
        control=DecisionShadowValidationControl(enabled=True),
        comparator=FailingComparison,
    )
    result = engine.validate(
        snapshot(LegacyDecisionSnapshot),
        snapshot(V2DecisionSnapshot),
    )
    assert result is not None
    assert result.classification is DecisionClassification.CRITICAL_DIVERGENCE
    assert result.error_codes == ("COMPARISON_ERROR",)
    assert "secret" not in result.model_dump_json()
