from sentinel.final_control_plane_readiness import (
    FINAL_CONTROL_PLANE_READINESS_ENABLED,
    ConsolidatedSignalsV1,
    FinalControlPlaneAggregator,
    FinalControlPlaneControl,
    FinalReadinessStatus,
)


def signals(**updates):
    values = {
        "authority_readiness_status": "APPROVED_FOR_MIGRATION",
        "safety_healthy": True,
        "recovery_status": "RECOVERY_OK",
        "state_corrupted": False,
        "evidence_available": True,
        "evidence_integrity_valid": True,
        "critical_data_loss": 0,
        "runtime_equivalence_rate": 1,
        "critical_divergences": 0,
        "operational_health": "HEALTHY",
        "trust_confidence": "TRUST_READY_REVIEW",
        "trust_score": 100,
        "trust_recommendation": "REQUEST_REVIEW",
        "controlled_activation_enabled": False,
        "v2_canary_enabled": False,
    }
    values.update(updates)
    return ConsolidatedSignalsV1(**values)


def test_disabled_by_default_does_not_evaluate() -> None:
    assert FINAL_CONTROL_PLANE_READINESS_ENABLED is False
    aggregator = FinalControlPlaneAggregator(control=FinalControlPlaneControl(environ={}))
    assert aggregator.evaluate(signals()) is None
    assert aggregator.metrics.snapshot().total_evaluations == 0


def test_complete_evidence_produces_high_confidence_review_only() -> None:
    result = FinalControlPlaneAggregator(control=FinalControlPlaneControl(enabled=True)).evaluate(signals())
    assert result.status is FinalReadinessStatus.HIGH_CONFIDENCE_REVIEW
    assert result.authority is False
    assert result.execution_requested is False
    assert len(result.evidence_hash) == 64
    assert set(result.passed_gates) == {
        "SAFETY",
        "EVIDENCE",
        "RUNTIME",
        "TRUST",
        "ACTIVATION",
    }


def test_insufficient_evidence_is_not_approval() -> None:
    result = FinalControlPlaneAggregator(control=FinalControlPlaneControl(enabled=True)).evaluate(
        signals(
            evidence_available=False,
            trust_score=None,
            trust_confidence="UNKNOWN",
            trust_recommendation="NO_RECOMMENDATION",
        )
    )
    assert result.status is FinalReadinessStatus.INSUFFICIENT_EVIDENCE
