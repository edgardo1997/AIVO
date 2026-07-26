"""Completely passive final contractual execution boundary."""

from __future__ import annotations

from sentinel.contracts import (
    AuditEventV1,
    AuthorizationGrantV1,
    DecisionResultV1,
    EvidenceSignalV1,
    ExecutionBoundaryDecisionResultV1,
    PolicyEvaluationResultV1,
    SandboxSimulationResultV1,
    ToolGatewayDecisionResultV1,
)
from sentinel.evidence_integrity import EvidenceVerifier
from sentinel.operational_telemetry_hub import (
    OperationalEventV1,
    OperationalMetricSnapshotV1,
    OperationalTelemetryHub,
)

from .audit import boundary_events
from .control import ExecutionBoundaryControl
from .decision import deterministic_decision_id
from .metrics import (
    ExecutionBoundaryMetrics,
    ExecutionBoundaryMetricSnapshotV1,
)
from .request import ExecutionRequestV1
from .risk import classify_boundary
from .validation import boundary_validation_errors


class ExecutionBoundaryEnvelopeV1(DecisionResultV1):
    decision: ExecutionBoundaryDecisionResultV1
    validation_errors: tuple[str, ...]
    audit_event: AuditEventV1
    operational_event: OperationalEventV1
    telemetry_snapshot: OperationalMetricSnapshotV1 | None
    metrics: ExecutionBoundaryMetricSnapshotV1
    telemetry_error: str | None = None


class PassiveExecutionBoundaryV2:
    """Evaluates readiness contracts and exposes no execution capability."""

    authority = False
    execution_requested = False

    def __init__(
        self,
        *,
        control: ExecutionBoundaryControl,
        verifier: EvidenceVerifier,
        telemetry_hub: OperationalTelemetryHub,
        metrics: ExecutionBoundaryMetrics | None = None,
    ) -> None:
        self.control = control
        self.verifier = verifier
        self.telemetry_hub = telemetry_hub
        self.metrics = metrics or ExecutionBoundaryMetrics()

    def evaluate(
        self,
        *,
        request: ExecutionRequestV1,
        grant: AuthorizationGrantV1,
        gateway: ToolGatewayDecisionResultV1,
        simulation: SandboxSimulationResultV1,
        policy: PolicyEvaluationResultV1,
        evidence: EvidenceSignalV1,
    ) -> ExecutionBoundaryEnvelopeV1 | None:
        if not self.control.enabled:
            return None
        errors = boundary_validation_errors(
            request=request,
            grant=grant,
            gateway=gateway,
            simulation=simulation,
            policy=policy,
            evidence=evidence,
            verifier=self.verifier,
            now=request.timestamp,
        )
        selected = classify_boundary(
            validation_errors=errors,
            gateway_decision=gateway.decision,
            simulation_status=simulation.status,
            policy_status=policy.policy_status,
            risk_level=simulation.risk_level,
        )
        result = ExecutionBoundaryDecisionResultV1(
            decision_id=deterministic_decision_id(request, selected.value, errors),
            correlation_id=request.correlation_id,
            evidence_hash=request.evidence_hash,
            issuer_id=request.issuer_id,
            authorization_reference=request.authorization_reference,
            gateway_reference=request.gateway_reference,
            simulation_reference=request.simulation_reference,
            policy_reference=request.policy_reference,
            action_category=request.action_category,
            scope=request.scope,
            simulation_status=request.simulation_status,
            risk_level=simulation.risk_level,
            decision=selected,
            confidence=0.0
            if errors
            else min(
                gateway.confidence,
                simulation.confidence,
                policy.confidence,
            ),
            timestamp=request.timestamp,
        )
        audit_event, operational_event = boundary_events(result, valid_origin=not errors)
        telemetry_snapshot, telemetry_error = self._record_telemetry(operational_event)
        self.metrics.record(selected)
        return ExecutionBoundaryEnvelopeV1(
            decision=result,
            validation_errors=errors,
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
