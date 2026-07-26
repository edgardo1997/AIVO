from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from sentinel.contracts import (
    AuditEventV1,
    DecisionResultV1,
    EvidenceIntegrityStatusV1,
    EvidenceSignalV1,
    HealthStateV1,
    HealthStatusV1,
    ReadinessResultV1,
    ReadinessStateValueV1,
    SimulationActionTypeV1,
    SimulationOutcomeV1,
    SimulationRiskLevelV1,
)
from sentinel.operational_telemetry_hub import (
    OperationalEventV1,
    OperationalTelemetryHub,
)
from sentinel.recommendation_engine import (
    RecommendationResultV1,
    RecommendationValue,
    RiskLevel,
)
from sentinel.recommendation_engine.evaluation import (
    RecommendationEvaluationV1,
)
from sentinel.recommendation_engine.explanation import (
    RecommendationExplanationV1,
)
from sentinel.recommendation_engine.metrics import (
    RecommendationMetricSnapshotV1,
)
from sentinel.shadow_decision_orchestrator import EquivalenceLevel
from sentinel.shadow_decision_orchestrator.comparison import ShadowComparisonV1
from sentinel.shadow_decision_orchestrator.divergence import DivergenceSeverity
from sentinel.shadow_decision_orchestrator.metrics import (
    ShadowDecisionMetricSnapshotV1,
)
from sentinel.shadow_decision_orchestrator.orchestrator import (
    ShadowDecisionResultV1,
)
from sentinel.simulation_engine import PassiveSimulationEngine, SimulationEngineControl
from sentinel.v2_trust_evaluation import (
    ConfidenceState,
    RecommendationState,
    TrustEvaluationResultV1,
)


def _contracts(risk=RiskLevel.MEDIUM):
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    correlation_id = "decision:simulation"
    evidence_hash = "a" * 64
    issuer_id = "sentinel.v2.test"
    decision = DecisionResultV1()
    evidence = EvidenceSignalV1(
        evidence_id="evidence:simulation",
        issuer_id=issuer_id,
        created_at=timestamp,
        correlation_id=correlation_id,
        payload_hash=evidence_hash,
        signature="A" * 88,
        integrity_status=EvidenceIntegrityStatusV1.VERIFIED,
    )
    health = HealthStatusV1(state=HealthStateV1.HEALTHY)
    readiness = ReadinessResultV1(
        status=ReadinessStateValueV1.READY_FOR_HUMAN_REVIEW,
        confidence=92,
        evidence_hash=evidence_hash,
        correlation_id=correlation_id,
    )
    audit = AuditEventV1(
        event_id="audit:simulation",
        event_type="DECISION_RECORDED",
        timestamp=timestamp,
        correlation_id=correlation_id,
        evidence_hash=evidence_hash,
        issuer_id=issuer_id,
        result="OBSERVED",
    )
    operational = OperationalEventV1(
        event_id="telemetry:simulation-source",
        correlation_id=correlation_id,
        evidence_hash=evidence_hash,
        issuer_id=issuer_id,
        timestamp=timestamp,
        event_type="DECISION_RECORDED",
        health_state=health.state,
        decision_state="OBSERVED",
        integrity_status=evidence.integrity_status,
    )
    trust = TrustEvaluationResultV1(
        confidence=ConfidenceState.HIGH_CONFIDENCE,
        score=92,
        positive_factors=("STABILITY_HIGH",),
        negative_factors=(),
        recommendation=RecommendationState.EXTEND_CANARY,
    )
    comparison = ShadowComparisonV1(
        classification=EquivalenceLevel.MATCH,
        confidence=92,
        severity=DivergenceSeverity.NONE,
        reasons=("LOGICAL_EQUIVALENCE",),
        timestamp=timestamp,
        correlation_id=correlation_id,
        issuer_id=issuer_id,
        evidence_hash=evidence_hash,
    )
    shadow = ShadowDecisionResultV1(
        correlation_id=correlation_id,
        evidence_hash=evidence_hash,
        issuer_id=issuer_id,
        timestamp=timestamp,
        comparison=comparison,
        trust=trust,
        readiness=readiness,
        health=health,
        audit_event=audit,
        operational_event=operational,
        telemetry_snapshot=None,
        metrics=ShadowDecisionMetricSnapshotV1(
            comparisons=1,
            matches=1,
            partial_matches=0,
            divergences=0,
            critical_divergences=0,
        ),
    )
    recommendation = RecommendationResultV1(
        correlation_id=correlation_id,
        evidence_hash=evidence_hash,
        issuer_id=issuer_id,
        timestamp=timestamp,
        evaluation=RecommendationEvaluationV1(
            recommendation=RecommendationValue.CONTINUE_OBSERVATION,
            risk=risk,
            confidence=92,
            equivalence=EquivalenceLevel.MATCH,
            divergence_count=0,
        ),
        explanation=RecommendationExplanationV1(
            reason="Continue passive observation.",
            confidence=92,
            risk=risk,
            health=health.state,
            readiness=readiness.status,
            equivalence=EquivalenceLevel.MATCH,
            divergence_count=0,
            evidence_status=evidence.integrity_status,
            signature_status=evidence.integrity_status,
            issuer_id=issuer_id,
            correlation_id=correlation_id,
            timestamp=timestamp,
        ),
        audit_event=audit,
        operational_event=operational,
        telemetry_snapshot=None,
        metrics=RecommendationMetricSnapshotV1(
            evaluations=1,
            review_recommendations=0,
            blocked_recommendations=0,
            observation_recommendations=1,
        ),
    )
    return {
        "decision": decision,
        "evidence": evidence,
        "recommendation": recommendation,
        "health": health,
        "readiness": readiness,
        "audit_event": audit,
        "trust": trust,
        "shadow": shadow,
    }


def _engine(tmp_path, *, enabled=True):
    telemetry = OperationalTelemetryHub(
        database_path=tmp_path / "simulation.sqlite3",
        enabled=True,
    )
    return (
        PassiveSimulationEngine(
            control=SimulationEngineControl(enabled=enabled),
            telemetry_hub=telemetry,
        ),
        telemetry,
    )


def test_simulation_is_deterministic_and_idempotent_in_telemetry(tmp_path):
    engine, telemetry = _engine(tmp_path)
    inputs = _contracts()
    try:
        first = engine.simulate(
            action_type=SimulationActionTypeV1.DELETE_FILE,
            target_class="USER_DOCUMENT",
            dependency_classes=("APPLICATION_X", "SERVICE_Y"),
            **inputs,
        )
        second = engine.simulate(
            action_type=SimulationActionTypeV1.DELETE_FILE,
            target_class="USER_DOCUMENT",
            dependency_classes=("SERVICE_Y", "APPLICATION_X"),
            **inputs,
        )
        assert first.simulation == second.simulation
        assert first.simulation.dependencies == ("APPLICATION_X", "SERVICE_Y")
        assert len(telemetry.timeline.latest()) == 1
    finally:
        telemetry.close()


def test_risk_rollback_and_impact_are_passive_predictions(tmp_path):
    engine, telemetry = _engine(tmp_path)
    try:
        result = engine.simulate(
            action_type=SimulationActionTypeV1.DELETE_FILE,
            target_class="USER_DOCUMENT",
            dependency_classes=("APPLICATION_X",),
            **_contracts(RiskLevel.MEDIUM),
        )
        simulation = result.simulation
        assert simulation.risk_level is SimulationRiskLevelV1.MEDIUM
        assert simulation.result_type is SimulationOutcomeV1.SIMULATION_WARNING
        assert simulation.rollback_available is True
        assert simulation.confirmation_required is True
        assert "hypothetically" in simulation.impact_summary
        assert simulation.confidence == 92
    finally:
        telemetry.close()


def test_critical_recommendation_blocks_simulation_result(tmp_path):
    engine, telemetry = _engine(tmp_path)
    try:
        result = engine.simulate(
            action_type=SimulationActionTypeV1.MODIFY_CONFIGURATION,
            target_class="APPLICATION_CONFIGURATION",
            dependency_classes=(),
            **_contracts(RiskLevel.CRITICAL),
        )
        assert result.simulation.risk_level is SimulationRiskLevelV1.CRITICAL
        assert result.simulation.result_type is (SimulationOutcomeV1.SIMULATION_BLOCKED)
    finally:
        telemetry.close()


def test_contract_is_immutable_rejects_unknown_fields_and_shares_provenance(
    tmp_path,
):
    engine, telemetry = _engine(tmp_path)
    inputs = _contracts()
    try:
        envelope = engine.simulate(
            action_type=SimulationActionTypeV1.STOP_PROCESS,
            target_class="APPLICATION_PROCESS",
            dependency_classes=(),
            **inputs,
        )
        simulation = envelope.simulation
        with pytest.raises(ValidationError):
            simulation.confidence = 0
        with pytest.raises(ValidationError):
            simulation.__class__.model_validate({**simulation.model_dump(), "unexpected": "value"})
        assert simulation.correlation_id == inputs["evidence"].correlation_id
        assert simulation.evidence_hash == inputs["evidence"].payload_hash
        assert envelope.audit_event.correlation_id == simulation.correlation_id
        assert envelope.operational_event.evidence_hash == simulation.evidence_hash
        assert simulation.authority is False
        assert simulation.execution_requested is False
    finally:
        telemetry.close()


def test_enabled_simulation_records_timeline_and_snapshot(tmp_path):
    engine, telemetry = _engine(tmp_path)
    try:
        envelope = engine.simulate(
            action_type=SimulationActionTypeV1.INSTALL_APPLICATION,
            target_class="APPLICATION_PACKAGE",
            dependency_classes=("PACKAGE_PROVIDER",),
            **_contracts(),
        )
        assert telemetry.timeline.latest() == (envelope.operational_event,)
        assert envelope.telemetry_snapshot is not None
    finally:
        telemetry.close()


def test_disabled_by_default_creates_no_result_or_storage(tmp_path):
    telemetry = OperationalTelemetryHub(
        database_path=tmp_path / "disabled.sqlite3",
        enabled=False,
    )
    engine = PassiveSimulationEngine(
        control=SimulationEngineControl(environ={}),
        telemetry_hub=telemetry,
    )
    result = engine.simulate(
        action_type=SimulationActionTypeV1.DELETE_FILE,
        target_class="USER_DOCUMENT",
        dependency_classes=(),
        **_contracts(),
    )
    assert result is None
    assert not (tmp_path / "disabled.sqlite3").exists()
