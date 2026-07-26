from datetime import UTC, datetime

from sentinel.contracts import (
    AuditEventV1,
    DecisionResultV1,
    EvidenceIntegrityStatusV1,
    EvidenceSignalV1,
    HealthStateV1,
    HealthStatusV1,
    ReadinessResultV1,
    ReadinessStateValueV1,
)
from sentinel.operational_telemetry_hub import (
    OperationalEventV1,
    OperationalTelemetryHub,
)
from sentinel.recommendation_engine import (
    PassiveRecommendationEngine,
    RecommendationEngineControl,
    RecommendationValue,
    RiskLevel,
)
from sentinel.shadow_decision_orchestrator import (
    ShadowContractSnapshotV1,
    ShadowDecisionOrchestrator,
    ShadowOrchestratorControl,
)
from sentinel.v2_trust_evaluation import TrustEvaluationControl, TrustEvaluator


class LogicalDecision(DecisionResultV1):
    state: str


def _snapshot(*, evidence_hash="a" * 64):
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    correlation_id = "decision:recommendation"
    issuer_id = "sentinel.v2.test"
    evidence = EvidenceSignalV1(
        evidence_id="evidence:recommendation",
        issuer_id=issuer_id,
        created_at=timestamp,
        correlation_id=correlation_id,
        payload_hash=evidence_hash,
        signature="A" * 88,
        integrity_status=EvidenceIntegrityStatusV1.VERIFIED,
    )
    decision = LogicalDecision(state="ALLOW")
    readiness = ReadinessResultV1(
        status=ReadinessStateValueV1.READY_FOR_HUMAN_REVIEW,
        confidence=90,
        evidence_hash=evidence_hash,
        correlation_id=correlation_id,
    )
    health = HealthStatusV1(state=HealthStateV1.HEALTHY)
    audit = AuditEventV1(
        event_id="audit:recommendation",
        event_type="DECISION_RECORDED",
        timestamp=timestamp,
        correlation_id=correlation_id,
        evidence_hash=evidence_hash,
        issuer_id=issuer_id,
        result="ALLOW",
    )
    operational = OperationalEventV1(
        event_id="telemetry:recommendation",
        correlation_id=correlation_id,
        evidence_hash=evidence_hash,
        issuer_id=issuer_id,
        timestamp=timestamp,
        event_type="DECISION_RECORDED",
        health_state=health.state,
        decision_state="ALLOW",
        integrity_status=evidence.integrity_status,
    )
    snapshot = ShadowContractSnapshotV1(
        decision=decision,
        evidence=evidence,
        readiness=readiness,
        health=health,
        audit_event=audit,
        operational_event=operational,
    )
    return snapshot


def _evaluate_shadow(tmp_path, legacy, v2):
    telemetry = OperationalTelemetryHub(
        database_path=tmp_path / "shadow.sqlite3",
        enabled=True,
    )
    orchestrator = ShadowDecisionOrchestrator(
        control=ShadowOrchestratorControl(enabled=True),
        telemetry_hub=telemetry,
        trust_evaluator=TrustEvaluator(control=TrustEvaluationControl(enabled=True)),
    )
    result = orchestrator.observe(legacy=legacy, v2=v2)
    telemetry.close()
    return result


def _engine(tmp_path, *, enabled=True):
    telemetry = OperationalTelemetryHub(
        database_path=tmp_path / "recommendation.sqlite3",
        enabled=True,
    )
    engine = PassiveRecommendationEngine(
        control=RecommendationEngineControl(enabled=enabled),
        telemetry_hub=telemetry,
    )
    return engine, telemetry


def test_deterministic_risk_confidence_explanation_and_recommendation(tmp_path):
    snapshot = _snapshot()
    shadow = _evaluate_shadow(tmp_path, snapshot, snapshot)
    engine, telemetry = _engine(tmp_path)
    try:
        inputs = {
            "decision": snapshot.decision,
            "evidence": snapshot.evidence,
            "audit_event": snapshot.audit_event,
            "operational_event": snapshot.operational_event,
            "health": snapshot.health,
            "readiness": shadow.readiness,
            "shadow": shadow,
            "trust": shadow.trust,
        }
        first = engine.evaluate(**inputs)
        second = engine.evaluate(**inputs)

        assert first.evaluation == second.evaluation
        assert first.explanation == second.explanation
        assert first.evaluation.risk is RiskLevel.LOW
        assert first.evaluation.recommendation is (RecommendationValue.SAFE_TO_REVIEW)
        assert first.explanation.reason
        assert first.explanation.confidence == first.evaluation.confidence
        assert first.explanation.issuer_id == snapshot.evidence.issuer_id
        assert first.explanation.correlation_id == snapshot.evidence.correlation_id
        assert first.explanation.timestamp == snapshot.evidence.created_at
        assert first.authority is False
        assert first.execution_requested is False
    finally:
        telemetry.close()


def test_critical_shadow_produces_block_recommendation(tmp_path):
    legacy = _snapshot(evidence_hash="a" * 64)
    v2 = _snapshot(evidence_hash="b" * 64)
    shadow = _evaluate_shadow(tmp_path, legacy, v2)
    engine, telemetry = _engine(tmp_path)
    try:
        result = engine.evaluate(
            decision=v2.decision,
            evidence=v2.evidence,
            audit_event=v2.audit_event,
            operational_event=v2.operational_event,
            health=v2.health,
            readiness=shadow.readiness,
            shadow=shadow,
            trust=shadow.trust,
        )
        assert result.evaluation.risk is RiskLevel.CRITICAL
        assert result.evaluation.recommendation is (RecommendationValue.BLOCK_RECOMMENDATION)
        assert result.explanation.divergence_count == 1
    finally:
        telemetry.close()


def test_recommendation_is_recorded_in_telemetry(tmp_path):
    snapshot = _snapshot()
    shadow = _evaluate_shadow(tmp_path, snapshot, snapshot)
    engine, telemetry = _engine(tmp_path)
    try:
        result = engine.evaluate(
            decision=snapshot.decision,
            evidence=snapshot.evidence,
            audit_event=snapshot.audit_event,
            operational_event=snapshot.operational_event,
            health=snapshot.health,
            readiness=shadow.readiness,
            shadow=shadow,
            trust=shadow.trust,
        )
        assert telemetry.timeline.latest() == (result.operational_event,)
        assert result.telemetry_snapshot is not None
        assert result.audit_event.correlation_id == result.correlation_id
        assert result.operational_event.evidence_hash == result.evidence_hash
    finally:
        telemetry.close()


def test_contract_provenance_mismatch_is_rejected(tmp_path):
    snapshot = _snapshot()
    shadow = _evaluate_shadow(tmp_path, snapshot, snapshot)
    engine, telemetry = _engine(tmp_path)
    altered = snapshot.audit_event.model_copy(update={"correlation_id": "decision:different"})
    try:
        try:
            engine.evaluate(
                decision=snapshot.decision,
                evidence=snapshot.evidence,
                audit_event=altered,
                operational_event=snapshot.operational_event,
                health=snapshot.health,
                readiness=shadow.readiness,
                shadow=shadow,
                trust=shadow.trust,
            )
        except ValueError as exc:
            assert str(exc) == "contract correlation mismatch"
        else:
            raise AssertionError("mismatched provenance was accepted")
    finally:
        telemetry.close()


def test_disabled_by_default_creates_no_storage_or_result(tmp_path):
    telemetry = OperationalTelemetryHub(
        database_path=tmp_path / "disabled.sqlite3",
        enabled=False,
    )
    engine = PassiveRecommendationEngine(
        control=RecommendationEngineControl(environ={}),
        telemetry_hub=telemetry,
    )
    assert engine.control.enabled is False
    assert not (tmp_path / "disabled.sqlite3").exists()
