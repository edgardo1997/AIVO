"""Passive orchestration of contract-only Legacy/V2 comparisons."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator

from sentinel.contracts import (
    AuditEventV1,
    DecisionResultV1,
    EvidenceSignalV1,
    HealthStateV1,
    HealthStatusV1,
    ReadinessResultV1,
    ReadinessStateValueV1,
)
from sentinel.contracts._base import FROZEN_MODEL_CONFIG, require_timezone
from sentinel.operational_telemetry_hub import (
    OperationalEventV1,
    OperationalMetricSnapshotV1,
    OperationalTelemetryHub,
)
from sentinel.v2_trust_evaluation import (
    TrustEvaluationResultV1,
    TrustEvaluator,
)

from .comparison import ShadowComparisonV1, compare_contracts
from .control import ShadowOrchestratorControl
from .equivalence import EquivalenceLevel
from .history import ShadowContractHistory
from .metrics import ShadowDecisionMetricSnapshotV1, ShadowDecisionMetrics

AwareDatetime = Annotated[datetime, AfterValidator(require_timezone)]


class ShadowContractSnapshotV1(DecisionResultV1):
    """Immutable snapshot containing central contracts only."""

    decision: DecisionResultV1
    evidence: EvidenceSignalV1
    readiness: ReadinessResultV1
    health: HealthStatusV1
    audit_event: AuditEventV1
    operational_event: OperationalEventV1


class ShadowDecisionResultV1(DecisionResultV1):
    """Passive comparison result with no runtime control capability."""

    model_config = FROZEN_MODEL_CONFIG

    correlation_id: str
    evidence_hash: str
    issuer_id: str
    timestamp: AwareDatetime
    comparison: ShadowComparisonV1
    trust: TrustEvaluationResultV1 | None
    readiness: ReadinessResultV1
    health: HealthStatusV1
    audit_event: AuditEventV1
    operational_event: OperationalEventV1
    telemetry_snapshot: OperationalMetricSnapshotV1 | None
    metrics: ShadowDecisionMetricSnapshotV1
    telemetry_error: str | None = None


class ShadowDecisionOrchestrator:
    """Observes emitted decisions and never participates in their authority."""

    authority = False
    execution_requested = False

    def __init__(
        self,
        *,
        control: ShadowOrchestratorControl,
        telemetry_hub: OperationalTelemetryHub,
        trust_evaluator: TrustEvaluator,
        history: ShadowContractHistory | None = None,
        metrics: ShadowDecisionMetrics | None = None,
    ) -> None:
        self.control = control
        self.telemetry_hub = telemetry_hub
        self.trust_evaluator = trust_evaluator
        self.history = history or ShadowContractHistory()
        self.metrics = metrics or ShadowDecisionMetrics()

    def observe(
        self,
        *,
        legacy: ShadowContractSnapshotV1,
        v2: ShadowContractSnapshotV1,
    ) -> ShadowDecisionResultV1 | None:
        if not self.control.enabled:
            return None

        comparison = compare_contracts(legacy, v2)
        audit_event = AuditEventV1(
            event_id=f"shadow-audit:{comparison.correlation_id.split(':')[-1]}",
            event_type="SHADOW_DECISION_COMPARISON",
            timestamp=comparison.timestamp,
            correlation_id=comparison.correlation_id,
            evidence_hash=comparison.evidence_hash,
            issuer_id=comparison.issuer_id,
            result=comparison.classification.value,
        )
        operational_event = OperationalEventV1(
            event_id=f"telemetry:{audit_event.event_id}",
            correlation_id=comparison.correlation_id,
            evidence_hash=comparison.evidence_hash,
            issuer_id=comparison.issuer_id,
            timestamp=comparison.timestamp,
            event_type=(f"SHADOW_DECISION_{comparison.classification.value}"),
            health_state=v2.health.state,
            decision_state=comparison.classification.value,
            integrity_status=v2.evidence.integrity_status,
        )

        telemetry_snapshot = None
        telemetry_error = None
        aggregator = self.telemetry_hub.aggregator
        if aggregator is None:
            telemetry_error = "TELEMETRY_DISABLED"
        else:
            try:
                telemetry_snapshot = aggregator.ingest(operational_event)
            except Exception as exc:
                telemetry_error = type(exc).__name__

        self.history.append(
            comparison,
            integrity=v2.evidence.integrity_status,
            health=v2.health.state,
        )
        trust = self.trust_evaluator.evaluate(self.history.trust_evidence())
        readiness = _readiness_from_contracts(
            decision=comparison,
            evidence=v2.evidence,
            operational_event=operational_event,
            audit_event=audit_event,
            health=v2.health,
        )
        self.metrics.record(comparison.classification)
        return ShadowDecisionResultV1(
            correlation_id=comparison.correlation_id,
            evidence_hash=comparison.evidence_hash,
            issuer_id=comparison.issuer_id,
            timestamp=comparison.timestamp,
            comparison=comparison,
            trust=trust,
            readiness=readiness,
            health=v2.health,
            audit_event=audit_event,
            operational_event=operational_event,
            telemetry_snapshot=telemetry_snapshot,
            metrics=self.metrics.snapshot(),
            telemetry_error=telemetry_error,
        )


def _readiness_from_contracts(
    *,
    decision: DecisionResultV1,
    evidence: EvidenceSignalV1,
    operational_event: OperationalEventV1,
    audit_event: AuditEventV1,
    health: HealthStatusV1,
) -> ReadinessResultV1:
    correlation_ids = {
        getattr(decision, "correlation_id", None),
        evidence.correlation_id,
        operational_event.correlation_id,
        audit_event.correlation_id,
    }
    evidence_hashes = {
        getattr(decision, "evidence_hash", None),
        evidence.payload_hash,
        operational_event.evidence_hash,
        audit_event.evidence_hash,
    }
    if len(correlation_ids) != 1 or len(evidence_hashes) != 1:
        status = ReadinessStateValueV1.BLOCKED
    elif health.state in {HealthStateV1.CRITICAL, HealthStateV1.DEGRADED}:
        status = ReadinessStateValueV1.BLOCKED
    else:
        classification = getattr(decision, "classification", None)
        status = {
            EquivalenceLevel.MATCH: (ReadinessStateValueV1.READY_FOR_HUMAN_REVIEW),
            EquivalenceLevel.PARTIAL_MATCH: (ReadinessStateValueV1.INSUFFICIENT_EVIDENCE),
            EquivalenceLevel.DIVERGENCE: (ReadinessStateValueV1.NOT_APPROVED),
            EquivalenceLevel.CRITICAL_DIVERGENCE: (ReadinessStateValueV1.BLOCKED),
        }.get(classification, ReadinessStateValueV1.INSUFFICIENT_EVIDENCE)
    return ReadinessResultV1(
        status=status,
        confidence=getattr(decision, "confidence", 0.0),
        evidence_hash=evidence.payload_hash,
        correlation_id=evidence.correlation_id,
    )
