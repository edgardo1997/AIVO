"""Passive recommendation consolidation over existing V2 contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator

from sentinel.contracts import (
    AuditEventV1,
    DecisionResultV1,
    EvidenceSignalV1,
    HealthStatusV1,
    ReadinessResultV1,
)
from sentinel.contracts._base import FROZEN_MODEL_CONFIG, require_timezone
from sentinel.operational_telemetry_hub import (
    OperationalEventV1,
    OperationalMetricSnapshotV1,
    OperationalTelemetryHub,
)
from sentinel.shadow_decision_orchestrator.orchestrator import (
    ShadowDecisionResultV1,
)
from sentinel.v2_trust_evaluation import TrustEvaluationResultV1

from .confidence import consolidated_confidence
from .control import RecommendationEngineControl
from .evaluation import RecommendationEvaluationV1
from .explanation import (
    RecommendationExplanationV1,
    explanation_reason,
)
from .metrics import RecommendationMetricSnapshotV1, RecommendationMetrics
from .recommendation import select_recommendation
from .risk import classify_risk

AwareDatetime = Annotated[datetime, AfterValidator(require_timezone)]


class RecommendationResultV1(DecisionResultV1):
    model_config = FROZEN_MODEL_CONFIG

    correlation_id: str
    evidence_hash: str
    issuer_id: str
    timestamp: AwareDatetime
    evaluation: RecommendationEvaluationV1
    explanation: RecommendationExplanationV1
    audit_event: AuditEventV1
    operational_event: OperationalEventV1
    telemetry_snapshot: OperationalMetricSnapshotV1 | None
    metrics: RecommendationMetricSnapshotV1
    telemetry_error: str | None = None


class PassiveRecommendationEngine:
    """Produces review-only recommendations and sanitized telemetry."""

    authority = False
    execution_requested = False

    def __init__(
        self,
        *,
        control: RecommendationEngineControl,
        telemetry_hub: OperationalTelemetryHub,
        metrics: RecommendationMetrics | None = None,
    ) -> None:
        self.control = control
        self.telemetry_hub = telemetry_hub
        self.metrics = metrics or RecommendationMetrics()

    def evaluate(
        self,
        *,
        decision: DecisionResultV1,
        evidence: EvidenceSignalV1,
        audit_event: AuditEventV1,
        operational_event: OperationalEventV1,
        health: HealthStatusV1,
        readiness: ReadinessResultV1,
        shadow: ShadowDecisionResultV1,
        trust: TrustEvaluationResultV1,
    ) -> RecommendationResultV1 | None:
        if not self.control.enabled:
            return None
        _validate_contract_provenance(
            decision=decision,
            evidence=evidence,
            audit_event=audit_event,
            operational_event=operational_event,
            health=health,
            readiness=readiness,
            shadow=shadow,
        )

        risk = classify_risk(
            trust=trust.confidence,
            health=health.state,
            readiness=readiness.status,
            equivalence=shadow.comparison.classification,
            integrity=evidence.integrity_status,
        )
        confidence = consolidated_confidence(
            shadow=shadow,
            trust=trust,
            readiness=readiness,
            integrity=evidence.integrity_status,
        )
        recommendation = select_recommendation(
            risk=risk,
            confidence=confidence,
            trust=trust.confidence,
            readiness=readiness.status,
            equivalence=shadow.comparison.classification,
            integrity=evidence.integrity_status,
        )
        divergence_count = shadow.metrics.divergences + shadow.metrics.critical_divergences
        evaluation = RecommendationEvaluationV1(
            recommendation=recommendation,
            risk=risk,
            confidence=confidence,
            equivalence=shadow.comparison.classification,
            divergence_count=divergence_count,
        )
        explanation = RecommendationExplanationV1(
            reason=explanation_reason(
                risk=risk,
                equivalence=shadow.comparison.classification,
                integrity=evidence.integrity_status,
            ),
            confidence=confidence,
            risk=risk,
            health=health.state,
            readiness=readiness.status,
            equivalence=shadow.comparison.classification,
            divergence_count=divergence_count,
            evidence_status=evidence.integrity_status,
            signature_status=evidence.integrity_status,
            issuer_id=evidence.issuer_id,
            correlation_id=evidence.correlation_id,
            timestamp=evidence.created_at,
        )
        result_audit = AuditEventV1(
            event_id=f"recommendation:{audit_event.event_id}",
            event_type="V2_RECOMMENDATION_RECORDED",
            timestamp=evidence.created_at,
            correlation_id=evidence.correlation_id,
            evidence_hash=evidence.payload_hash,
            issuer_id=evidence.issuer_id,
            result=recommendation.value,
        )
        result_operational = OperationalEventV1(
            event_id=f"telemetry:{result_audit.event_id}",
            correlation_id=evidence.correlation_id,
            evidence_hash=evidence.payload_hash,
            issuer_id=evidence.issuer_id,
            timestamp=evidence.created_at,
            event_type="V2_RECOMMENDATION_RECORDED",
            health_state=health.state,
            decision_state=recommendation.value,
            integrity_status=evidence.integrity_status,
        )
        telemetry_snapshot = None
        telemetry_error = None
        aggregator = self.telemetry_hub.aggregator
        if aggregator is None:
            telemetry_error = "TELEMETRY_DISABLED"
        else:
            try:
                telemetry_snapshot = aggregator.ingest(result_operational)
            except Exception as exc:
                telemetry_error = type(exc).__name__

        self.metrics.record(recommendation)
        return RecommendationResultV1(
            correlation_id=evidence.correlation_id,
            evidence_hash=evidence.payload_hash,
            issuer_id=evidence.issuer_id,
            timestamp=evidence.created_at,
            evaluation=evaluation,
            explanation=explanation,
            audit_event=result_audit,
            operational_event=result_operational,
            telemetry_snapshot=telemetry_snapshot,
            metrics=self.metrics.snapshot(),
            telemetry_error=telemetry_error,
        )


def _validate_contract_provenance(
    *,
    decision: DecisionResultV1,
    evidence: EvidenceSignalV1,
    audit_event: AuditEventV1,
    operational_event: OperationalEventV1,
    health: HealthStatusV1,
    readiness: ReadinessResultV1,
    shadow: ShadowDecisionResultV1,
) -> None:
    correlation_ids = {
        evidence.correlation_id,
        audit_event.correlation_id,
        operational_event.correlation_id,
        readiness.correlation_id,
        shadow.correlation_id,
    }
    evidence_hashes = {
        evidence.payload_hash,
        audit_event.evidence_hash,
        operational_event.evidence_hash,
        readiness.evidence_hash,
        shadow.evidence_hash,
    }
    if hasattr(decision, "correlation_id"):
        correlation_ids.add(decision.correlation_id)
    if hasattr(decision, "evidence_hash"):
        evidence_hashes.add(decision.evidence_hash)
    if len(correlation_ids) != 1:
        raise ValueError("contract correlation mismatch")
    if len(evidence_hashes) != 1:
        raise ValueError("contract evidence mismatch")
    if operational_event.issuer_id != evidence.issuer_id:
        raise ValueError("contract issuer mismatch")
    if audit_event.issuer_id != evidence.issuer_id:
        raise ValueError("contract issuer mismatch")
    if operational_event.health_state is not health.state:
        raise ValueError("contract health mismatch")
