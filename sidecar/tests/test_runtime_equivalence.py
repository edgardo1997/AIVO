from sentinel.runtime_equivalence_validation import (
    RUNTIME_EQUIVALENCE_VALIDATION_ENABLED,
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
        "event_sequence": ("INTENT", "PLAN", "POLICY", "RESULT"),
        "execution_timing_ms": 100,
        "return_code": "OK",
    }
    values.update(updates)
    return RuntimeEquivalenceSnapshotV1(**values)


def test_disabled_by_default_does_nothing() -> None:
    assert RUNTIME_EQUIVALENCE_VALIDATION_ENABLED is False
    validator = RuntimeEquivalenceValidator(control=RuntimeEquivalenceControl(environ={}))
    assert validator.validate(snapshot("LEGACY"), snapshot("V2")) is None
    assert validator.metrics.snapshot().comparisons == 0


def test_equivalent_runtime_result_is_immutable_and_non_authoritative() -> None:
    validator = RuntimeEquivalenceValidator(control=RuntimeEquivalenceControl(enabled=True))
    result = validator.validate(snapshot("LEGACY"), snapshot("V2"))
    assert result is not None
    assert result.classification is EquivalenceClassification.EQUIVALENT
    assert result.differences == ()
    assert result.metrics.matching_fields == result.metrics.compared_fields
    assert result.authority is False
    assert result.timestamp.utcoffset() is not None
    try:
        result.authority = True
    except Exception:
        pass
    assert result.authority is False


def test_errors_are_isolated_and_sanitized() -> None:
    class BrokenComparator:
        def compare(self, legacy, v2):
            raise RuntimeError("private secret")

    validator = RuntimeEquivalenceValidator(
        control=RuntimeEquivalenceControl(enabled=True),
        comparator=BrokenComparator(),
    )
    result = validator.validate(snapshot("LEGACY"), snapshot("V2"))
    assert result is not None
    assert result.classification is EquivalenceClassification.UNKNOWN
    assert result.differences == ("COMPARISON_ERROR",)
    assert "private secret" not in result.model_dump_json()
