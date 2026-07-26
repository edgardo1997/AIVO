import pytest

from sentinel.final_control_plane_readiness import (
    ConsolidatedSignalsV1,
    FinalControlPlaneAggregator,
    FinalControlPlaneControl,
    FinalReadinessStatus,
)


def base(**updates):
    values = {
        "authority_readiness_status": "READY_FOR_REVIEW",
        "safety_healthy": True,
        "recovery_status": "SAFE_RECOVERY",
        "state_corrupted": False,
        "evidence_available": True,
        "evidence_integrity_valid": True,
        "critical_data_loss": 0,
        "runtime_equivalence_rate": 0.995,
        "critical_divergences": 0,
        "operational_health": "HEALTHY",
        "trust_confidence": "HIGH_CONFIDENCE",
        "trust_score": 80,
        "trust_recommendation": "EXTEND_CANARY",
        "controlled_activation_enabled": False,
        "v2_canary_enabled": False,
    }
    values.update(updates)
    return ConsolidatedSignalsV1(**values)


def evaluate(**updates):
    return FinalControlPlaneAggregator(control=FinalControlPlaneControl(enabled=True)).evaluate(base(**updates))


def test_all_gates_pass_for_human_review() -> None:
    result = evaluate()
    assert result.status is FinalReadinessStatus.READY_FOR_HUMAN_REVIEW
    assert result.failed_gates == ()


@pytest.mark.parametrize(
    ("field", "value", "gate"),
    [
        ("state_corrupted", True, "SAFETY"),
        ("evidence_integrity_valid", False, "EVIDENCE"),
        ("critical_divergences", 1, "RUNTIME"),
        ("trust_recommendation", "BLOCK_MIGRATION", "TRUST"),
        ("controlled_activation_enabled", True, "ACTIVATION"),
        ("v2_canary_enabled", True, "ACTIVATION"),
    ],
)
def test_blocking_gate_conditions(field, value, gate) -> None:
    result = evaluate(**{field: value})
    assert result.status is FinalReadinessStatus.BLOCKED
    assert gate in result.failed_gates


def test_status_vocabulary_contains_no_activation_or_cutover() -> None:
    assert set(FinalReadinessStatus.__members__) == {
        "BLOCKED",
        "INSUFFICIENT_EVIDENCE",
        "READY_FOR_HUMAN_REVIEW",
        "HIGH_CONFIDENCE_REVIEW",
        "NOT_APPROVED",
    }
