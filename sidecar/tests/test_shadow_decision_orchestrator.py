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
from sentinel.shadow_decision_orchestrator import (
    EquivalenceLevel,
    ShadowContractSnapshotV1,
    ShadowDecisionOrchestrator,
    ShadowOrchestratorControl,
)
from sentinel.v2_trust_evaluation import TrustEvaluationControl, TrustEvaluator


class LogicalDecision(DecisionResultV1):
    state: str


def _snapshot(
    *,
    state: str = "ALLOW",
    correlation_id: str = "decision:shared",
    evidence_hash: str = "a" * 64,
    issuer_id: str = "sentinel.v2.test",
    health: HealthStateV1 = HealthStateV1.HEALTHY,
    readiness: ReadinessStateValueV1 = (ReadinessStateValueV1.READY_FOR_HUMAN_REVIEW),
    audit_result: str = "ALLOW",
) -> ShadowContractSnapshotV1:
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    evidence = EvidenceSignalV1(
        evidence_id="evidence:shared",
        issuer_id=issuer_id,
        created_at=timestamp,
        correlation_id=correlation_id,
        payload_hash=evidence_hash,
        signature="A" * 88,
        integrity_status=EvidenceIntegrityStatusV1.VERIFIED,
    )
    return ShadowContractSnapshotV1(
        decision=LogicalDecision(state=state),
        evidence=evidence,
        readiness=ReadinessResultV1(
            status=readiness,
            confidence=90,
            evidence_hash=evidence_hash,
            correlation_id=correlation_id,
        ),
        health=HealthStatusV1(state=health),
        audit_event=AuditEventV1(
            event_id="audit:shared",
            event_type="DECISION_RECORDED",
            timestamp=timestamp,
            correlation_id=correlation_id,
            evidence_hash=evidence_hash,
            issuer_id=issuer_id,
            result=audit_result,
        ),
        operational_event=OperationalEventV1(
            event_id="telemetry:shared",
            correlation_id=correlation_id,
            evidence_hash=evidence_hash,
            issuer_id=issuer_id,
            timestamp=timestamp,
            event_type="DECISION_RECORDED",
            health_state=health,
            decision_state=state,
            integrity_status=EvidenceIntegrityStatusV1.VERIFIED,
        ),
    )


def _orchestrator(tmp_path, *, enabled=True):
    telemetry = OperationalTelemetryHub(
        database_path=tmp_path / "shadow.sqlite3",
        enabled=True,
    )
    evaluator = TrustEvaluator(control=TrustEvaluationControl(enabled=True))
    orchestrator = ShadowDecisionOrchestrator(
        control=ShadowOrchestratorControl(enabled=enabled),
        telemetry_hub=telemetry,
        trust_evaluator=evaluator,
    )
    return orchestrator, telemetry


def test_match_is_deterministic_and_updates_trust_readiness_and_telemetry(
    tmp_path,
):
    orchestrator, telemetry = _orchestrator(tmp_path)
    try:
        legacy = _snapshot()
        v2 = _snapshot()
        first = orchestrator.observe(legacy=legacy, v2=v2)

        assert first.comparison.classification is EquivalenceLevel.MATCH
        assert first.comparison.confidence == 100
        assert first.trust is not None
        assert first.readiness.status is (ReadinessStateValueV1.READY_FOR_HUMAN_REVIEW)
        assert telemetry.timeline.latest() == (first.operational_event,)
        assert first.telemetry_snapshot.decisions == 1
        assert first.authority is False
        assert first.execution_requested is False

        second_orchestrator, second_telemetry = _orchestrator(tmp_path / "second")
        try:
            second = second_orchestrator.observe(legacy=legacy, v2=v2)
            assert first.comparison == second.comparison
        finally:
            second_telemetry.close()
    finally:
        telemetry.close()


def test_partial_match_for_auxiliary_contract_difference(tmp_path):
    orchestrator, telemetry = _orchestrator(tmp_path)
    try:
        result = orchestrator.observe(
            legacy=_snapshot(),
            v2=_snapshot(
                health=HealthStateV1.WARNING,
                audit_result="OBSERVED",
            ),
        )
        assert result.comparison.classification is EquivalenceLevel.PARTIAL_MATCH
        assert result.readiness.status is (ReadinessStateValueV1.INSUFFICIENT_EVIDENCE)
    finally:
        telemetry.close()


def test_divergence_for_logical_decision_difference(tmp_path):
    orchestrator, telemetry = _orchestrator(tmp_path)
    try:
        result = orchestrator.observe(
            legacy=_snapshot(state="ALLOW"),
            v2=_snapshot(state="DENY"),
        )
        assert result.comparison.classification is EquivalenceLevel.DIVERGENCE
        assert result.readiness.status is ReadinessStateValueV1.NOT_APPROVED
    finally:
        telemetry.close()


def test_critical_divergence_for_provenance_difference(tmp_path):
    orchestrator, telemetry = _orchestrator(tmp_path)
    try:
        result = orchestrator.observe(
            legacy=_snapshot(),
            v2=_snapshot(evidence_hash="b" * 64),
        )
        assert result.comparison.classification is (EquivalenceLevel.CRITICAL_DIVERGENCE)
        assert result.readiness.status is ReadinessStateValueV1.BLOCKED
    finally:
        telemetry.close()


def test_shadow_result_shares_v2_provenance(tmp_path):
    orchestrator, telemetry = _orchestrator(tmp_path)
    try:
        v2 = _snapshot()
        result = orchestrator.observe(legacy=_snapshot(), v2=v2)
        derived = (
            result.comparison,
            result.audit_event,
            result.operational_event,
        )
        assert {item.correlation_id for item in derived} == {v2.evidence.correlation_id}
        assert {item.evidence_hash for item in derived} == {v2.evidence.payload_hash}
        assert result.readiness.correlation_id == v2.evidence.correlation_id
        assert result.readiness.evidence_hash == v2.evidence.payload_hash
    finally:
        telemetry.close()


def test_disabled_by_default_does_not_observe(tmp_path):
    telemetry = OperationalTelemetryHub(
        database_path=tmp_path / "unused.sqlite3",
        enabled=False,
    )
    orchestrator = ShadowDecisionOrchestrator(
        control=ShadowOrchestratorControl(environ={}),
        telemetry_hub=telemetry,
        trust_evaluator=TrustEvaluator(control=TrustEvaluationControl(enabled=False)),
    )
    assert orchestrator.observe(legacy=_snapshot(), v2=_snapshot()) is None
    assert not (tmp_path / "unused.sqlite3").exists()
