"""Passive deterministic simulation coordinator."""

from __future__ import annotations

import hashlib
import json

from sentinel.contracts import (
    AuditEventV1,
    DecisionResultV1,
    EvidenceSignalV1,
    HealthStatusV1,
    ReadinessResultV1,
    SimulationActionTypeV1,
    SimulationResultV1,
    SimulationRiskLevelV1,
)
from sentinel.operational_telemetry_hub import (
    OperationalEventV1,
    OperationalMetricSnapshotV1,
    OperationalTelemetryHub,
)
from sentinel.recommendation_engine import RecommendationResultV1
from sentinel.shadow_decision_orchestrator.orchestrator import (
    ShadowDecisionResultV1,
)
from sentinel.v2_trust_evaluation import TrustEvaluationResultV1

from .analysis import simulation_confidence
from .control import SimulationEngineControl
from .dependencies import known_dependencies
from .impact import describe_impact
from .metrics import SimulationMetrics, SimulationMetricSnapshotV1
from .risk import inherited_risk
from .rollback import assess_rollback


class SimulationEnvelopeV1(DecisionResultV1):
    simulation: SimulationResultV1
    audit_event: AuditEventV1
    operational_event: OperationalEventV1
    telemetry_snapshot: OperationalMetricSnapshotV1 | None
    metrics: SimulationMetricSnapshotV1
    telemetry_error: str | None = None


class PassiveSimulationEngine:
    """Predicts contract-level impact and cannot invoke any action."""

    authority = False
    execution_requested = False

    def __init__(
        self,
        *,
        control: SimulationEngineControl,
        telemetry_hub: OperationalTelemetryHub,
        metrics: SimulationMetrics | None = None,
    ) -> None:
        self.control = control
        self.telemetry_hub = telemetry_hub
        self.metrics = metrics or SimulationMetrics()

    def simulate(
        self,
        *,
        action_type: SimulationActionTypeV1,
        target_class: str,
        dependency_classes: tuple[str, ...],
        decision: DecisionResultV1,
        evidence: EvidenceSignalV1,
        recommendation: RecommendationResultV1,
        health: HealthStatusV1,
        readiness: ReadinessResultV1,
        audit_event: AuditEventV1,
        trust: TrustEvaluationResultV1,
        shadow: ShadowDecisionResultV1,
    ) -> SimulationEnvelopeV1 | None:
        if not self.control.enabled:
            return None
        _validate_provenance(
            decision=decision,
            evidence=evidence,
            recommendation=recommendation,
            health=health,
            readiness=readiness,
            audit_event=audit_event,
            shadow=shadow,
        )
        dependencies = known_dependencies(dependency_classes)
        impact_summary, estimated_effect = describe_impact(action_type)
        rollback_available, rollback_complexity = assess_rollback(action_type)
        risk, outcome = inherited_risk(recommendation.evaluation.risk)
        confidence = simulation_confidence(
            recommendation=recommendation,
            trust=trust,
            readiness=readiness,
            shadow=shadow,
            integrity=evidence.integrity_status,
        )
        simulation_id = _simulation_id(
            correlation_id=evidence.correlation_id,
            evidence_hash=evidence.payload_hash,
            action_type=action_type,
            target_class=target_class,
            dependencies=dependencies,
        )
        simulation = SimulationResultV1(
            simulation_id=simulation_id,
            correlation_id=evidence.correlation_id,
            evidence_hash=evidence.payload_hash,
            issuer_id=evidence.issuer_id,
            timestamp=evidence.created_at,
            action_type=action_type,
            target_class=target_class,
            result_type=outcome,
            risk_level=risk,
            impact_summary=impact_summary,
            dependencies=dependencies,
            rollback_available=rollback_available,
            rollback_complexity=rollback_complexity,
            estimated_effect=estimated_effect,
            confirmation_required=risk is not SimulationRiskLevelV1.LOW,
            confidence=confidence,
        )
        simulation_audit = AuditEventV1(
            event_id=f"audit:{simulation_id}",
            event_type="V2_SIMULATION_RECORDED",
            timestamp=evidence.created_at,
            correlation_id=evidence.correlation_id,
            evidence_hash=evidence.payload_hash,
            issuer_id=evidence.issuer_id,
            result=outcome.value,
        )
        operational_event = OperationalEventV1(
            event_id=f"telemetry:{simulation_id}",
            correlation_id=evidence.correlation_id,
            evidence_hash=evidence.payload_hash,
            issuer_id=evidence.issuer_id,
            timestamp=evidence.created_at,
            event_type="V2_SIMULATION_RECORDED",
            health_state=health.state,
            decision_state=outcome.value,
            integrity_status=evidence.integrity_status,
        )
        telemetry_snapshot, telemetry_error = self._record_telemetry(operational_event)
        self.metrics.record(outcome)
        return SimulationEnvelopeV1(
            simulation=simulation,
            audit_event=simulation_audit,
            operational_event=operational_event,
            telemetry_snapshot=telemetry_snapshot,
            metrics=self.metrics.snapshot(),
            telemetry_error=telemetry_error,
        )

    def _record_telemetry(
        self,
        event: OperationalEventV1,
    ) -> tuple[OperationalMetricSnapshotV1 | None, str | None]:
        aggregator = self.telemetry_hub.aggregator
        storage = self.telemetry_hub.storage
        if aggregator is None or storage is None:
            return None, "TELEMETRY_DISABLED"
        try:
            existing = storage.read_event(event.event_id)
            if existing is not None:
                if existing != event:
                    return None, "TELEMETRY_CONFLICT"
                return aggregator.metrics.snapshot(), None
            return aggregator.ingest(event), None
        except Exception as exc:
            return None, type(exc).__name__


def _simulation_id(
    *,
    correlation_id: str,
    evidence_hash: str,
    action_type: SimulationActionTypeV1,
    target_class: str,
    dependencies: tuple[str, ...],
) -> str:
    canonical = json.dumps(
        {
            "action_type": action_type.value,
            "correlation_id": correlation_id,
            "dependencies": dependencies,
            "evidence_hash": evidence_hash,
            "target_class": target_class,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"simulation:{digest[:32]}"


def _validate_provenance(
    *,
    decision: DecisionResultV1,
    evidence: EvidenceSignalV1,
    recommendation: RecommendationResultV1,
    health: HealthStatusV1,
    readiness: ReadinessResultV1,
    audit_event: AuditEventV1,
    shadow: ShadowDecisionResultV1,
) -> None:
    correlation_ids = {
        evidence.correlation_id,
        recommendation.correlation_id,
        readiness.correlation_id,
        audit_event.correlation_id,
        shadow.correlation_id,
    }
    evidence_hashes = {
        evidence.payload_hash,
        recommendation.evidence_hash,
        readiness.evidence_hash,
        audit_event.evidence_hash,
        shadow.evidence_hash,
    }
    if hasattr(decision, "correlation_id"):
        correlation_ids.add(decision.correlation_id)
    if hasattr(decision, "evidence_hash"):
        evidence_hashes.add(decision.evidence_hash)
    if len(correlation_ids) != 1 or len(evidence_hashes) != 1:
        raise ValueError("simulation contract provenance mismatch")
    if recommendation.explanation.health is not health.state:
        raise ValueError("simulation health mismatch")
    if recommendation.explanation.readiness is not readiness.status:
        raise ValueError("simulation readiness mismatch")
