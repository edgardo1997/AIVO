from sentinel.runtime_equivalence_validation import (
    EquivalenceClassification,
    RuntimeEquivalenceControl,
    RuntimeEquivalenceSnapshotV1,
    RuntimeEquivalenceValidator,
)


def snapshot(runtime_type, **updates):
    values = {
        "runtime_type": runtime_type,
        "intent_hash": "a" * 64,
        "execution_plan_hash": "b" * 64,
        "discovery_hash": "c" * 64,
        "policy_hash": "d" * 64,
        "authorization_hash": "e" * 64,
        "runtime_status": "COMPLETED",
        "execution_result": "SUCCESS",
        "tool_selection_hash": "f" * 64,
        "event_sequence": ("INTENT", "PLAN", "RESULT"),
        "execution_timing_ms": 100,
        "return_code": "OK",
    }
    values.update(updates)
    return RuntimeEquivalenceSnapshotV1(**values)


def validate(**v2_updates):
    return RuntimeEquivalenceValidator(control=RuntimeEquivalenceControl(enabled=True)).validate(
        snapshot("LEGACY"), snapshot("V2", **v2_updates)
    )


def test_functional_difference() -> None:
    result = validate(execution_plan_hash="0" * 64)
    assert result.classification is EquivalenceClassification.FUNCTIONAL_DIFFERENCE
    assert "EXECUTION_PLAN" in result.differences


def test_security_difference() -> None:
    result = validate(authorization_hash="0" * 64)
    assert result.classification is EquivalenceClassification.SECURITY_DIFFERENCE
    assert "AUTHORIZATION" in result.differences


def test_unexpected_execution_result() -> None:
    result = validate(execution_result="FAILURE", return_code="ERROR")
    assert result.classification is EquivalenceClassification.UNEXPECTED_RESULT


def test_timing_difference_respects_tolerance() -> None:
    result = validate(execution_timing_ms=500)
    assert result.classification is EquivalenceClassification.TIMING_DIFFERENCE
    assert result.metrics.timing_delta_ms == 400
