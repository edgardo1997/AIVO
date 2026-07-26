"""Passive V2 policy evaluation coordinator."""

from __future__ import annotations

import hashlib

from sentinel.contracts import (
    AuditEventV1,
    DecisionResultV1,
    EvidenceSignalV1,
    HealthStatusV1,
    PolicyEvaluationResultV1,
    ReadinessResultV1,
    SimulationResultV1,
)
from sentinel.operational_telemetry_hub import (
    OperationalEventV1,
    OperationalMetricSnapshotV1,
    OperationalTelemetryHub,
)
from sentinel.recommendation_engine import RecommendationResultV1
from sentinel.v2_trust_evaluation import TrustEvaluationResultV1

from .control import PolicyEngineControl
from .decision import select_policy_status
from .evaluation import policy_confidence
from .exceptions import PolicyContractMismatchError
from .metrics import PolicyMetrics, PolicyMetricSnapshotV1
from .risk import inherited_policy_risk
from .rules import evaluate_rules

_POLICY_ID = "policy:sentinel-v2-passive:1"


class PolicyEvaluationEnvelopeV1(DecisionResultV1):
    evaluation: PolicyEvaluationResultV1
    audit_event: AuditEventV1
    operational_event: OperationalEventV1
    telemetry_snapshot: OperationalMetricSnapshotV1 | None
    metrics: PolicyMetricSnapshotV1
    telemetry_error: str | None = None


class PassivePolicyEngine:
    """Evaluates policy compatibility and can never authorize an action."""

    authority = False
    execution_requested = False

    def __init__(
        self,
        *,
        control: PolicyEngineControl,
        telemetry_hub: OperationalTelemetryHub,
        metrics: PolicyMetrics | None = None,
    ) -> None:
        self.control = control
        self.telemetry_hub = telemetry_hub
        self.metrics = metrics or PolicyMetrics()

    def evaluate(
        self,
        *,
        decision: DecisionResultV1,
        recommendation: RecommendationResultV1,
        simulation: SimulationResultV1,
        evidence: EvidenceSignalV1,
        trust: TrustEvaluationResultV1,
        readiness: ReadinessResultV1,
        health: HealthStatusV1,
    ) -> PolicyEvaluationEnvelopeV1 | None:
        if not self.control.enabled:
            return None
        _validate_provenance(
            decision=decision,
            recommendation=recommendation,
            simulation=simulation,
            evidence=evidence,
            readiness=readiness,
            health=health,
        )
        rules = evaluate_rules(
            simulation=simulation,
            recommendation=recommendation,
            trust=trust,
            readiness=readiness.status,
            health=health.state,
            integrity=evidence.integrity_status,
        )
        status = select_policy_status(rules)
        confidence = policy_confidence(
            simulation=simulation,
            recommendation=recommendation,
            trust=trust,
            readiness=readiness,
            integrity=evidence.integrity_status,
        )
        evaluation = PolicyEvaluationResultV1(
            policy_id=_POLICY_ID,
            correlation_id=evidence.correlation_id,
            evidence_hash=evidence.payload_hash,
            issuer_id=evidence.issuer_id,
            timestamp=evidence.created_at,
            action_type=simulation.action_type,
            risk_level=inherited_policy_risk(simulation),
            policy_status=status,
            violations=rules.violations,
            requirements=rules.requirements,
            confidence=confidence,
        )
        event_suffix = hashlib.sha256(
            (f"{evaluation.correlation_id}:{evaluation.evidence_hash}:{evaluation.action_type.value}").encode("utf-8")
        ).hexdigest()[:24]
        audit_event = AuditEventV1(
            event_id=f"policy-audit:{event_suffix}",
            event_type="V2_POLICY_EVALUATED",
            timestamp=evidence.created_at,
            correlation_id=evidence.correlation_id,
            evidence_hash=evidence.payload_hash,
            issuer_id=evidence.issuer_id,
            result=status.value,
        )
        operational_event = OperationalEventV1(
            event_id=f"telemetry:policy:{event_suffix}",
            correlation_id=evidence.correlation_id,
            evidence_hash=evidence.payload_hash,
            issuer_id=evidence.issuer_id,
            timestamp=evidence.created_at,
            event_type="V2_POLICY_EVALUATED",
            health_state=health.state,
            decision_state=status.value,
            integrity_status=evidence.integrity_status,
        )
        telemetry_snapshot, telemetry_error = self._record_telemetry(operational_event)
        self.metrics.record(status)
        return PolicyEvaluationEnvelopeV1(
            evaluation=evaluation,
            audit_event=audit_event,
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


def _validate_provenance(
    *,
    decision: DecisionResultV1,
    recommendation: RecommendationResultV1,
    simulation: SimulationResultV1,
    evidence: EvidenceSignalV1,
    readiness: ReadinessResultV1,
    health: HealthStatusV1,
) -> None:
    correlation_ids = {
        recommendation.correlation_id,
        simulation.correlation_id,
        evidence.correlation_id,
        readiness.correlation_id,
    }
    evidence_hashes = {
        recommendation.evidence_hash,
        simulation.evidence_hash,
        evidence.payload_hash,
        readiness.evidence_hash,
    }
    if hasattr(decision, "correlation_id"):
        correlation_ids.add(decision.correlation_id)
    if hasattr(decision, "evidence_hash"):
        evidence_hashes.add(decision.evidence_hash)
    if len(correlation_ids) != 1 or len(evidence_hashes) != 1:
        raise PolicyContractMismatchError("policy input contracts do not share provenance")
    if recommendation.issuer_id != evidence.issuer_id:
        raise PolicyContractMismatchError("policy issuer mismatch")
    if recommendation.explanation.health is not health.state:
        raise PolicyContractMismatchError("policy health mismatch")
    if recommendation.explanation.readiness is not readiness.status:
        raise PolicyContractMismatchError("policy readiness mismatch")
