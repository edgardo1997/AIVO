"""Passive Sandbox Engine V2 simulation coordinator."""

from __future__ import annotations

import hashlib

from sentinel.contracts import (
    AuditEventV1,
    AuthorizationGrantV1,
    DecisionResultV1,
    EvidenceSignalV1,
    SandboxSimulationResultV1,
    ToolGatewayDecisionResultV1,
)
from sentinel.evidence_integrity import EvidenceVerifier
from sentinel.operational_telemetry_hub import (
    OperationalEventV1,
    OperationalMetricSnapshotV1,
    OperationalTelemetryHub,
)

from .audit import sandbox_events
from .control import SandboxEngineControl
from .decision import simulation_status
from .environment import HypotheticalEnvironmentV1, hypothetical_environment
from .impact import estimated_impact
from .metrics import SandboxMetrics, SandboxMetricSnapshotV1
from .request import SandboxRequestV1
from .rollback import rollback_is_predicted
from .validation import validation_errors


class SandboxEvaluationEnvelopeV1(DecisionResultV1):
    simulation: SandboxSimulationResultV1
    environment: HypotheticalEnvironmentV1
    validation_errors: tuple[str, ...]
    audit_event: AuditEventV1
    operational_event: OperationalEventV1
    telemetry_snapshot: OperationalMetricSnapshotV1 | None
    metrics: SandboxMetricSnapshotV1
    telemetry_error: str | None = None


class PassiveSandboxEngineV2:
    """Produces hypothetical impact only; no environment is instantiated."""

    authority = False
    execution_requested = False

    def __init__(
        self,
        *,
        control: SandboxEngineControl,
        verifier: EvidenceVerifier,
        telemetry_hub: OperationalTelemetryHub,
        metrics: SandboxMetrics | None = None,
    ) -> None:
        self.control = control
        self.verifier = verifier
        self.telemetry_hub = telemetry_hub
        self.metrics = metrics or SandboxMetrics()

    def simulate(
        self,
        *,
        request: SandboxRequestV1,
        gateway: ToolGatewayDecisionResultV1,
        grant: AuthorizationGrantV1,
        evidence: EvidenceSignalV1,
    ) -> SandboxEvaluationEnvelopeV1 | None:
        if not self.control.enabled:
            return None
        errors = validation_errors(
            request=request,
            gateway=gateway,
            grant=grant,
            evidence=evidence,
            verifier=self.verifier,
            now=request.timestamp,
        )
        status = simulation_status(
            gateway_decision=gateway.decision,
            risk=gateway.risk_level,
            validation_errors=errors,
        )
        simulation_id = _simulation_id(
            request=request,
            gateway=gateway,
            status=status.value,
            errors=errors,
        )
        result = SandboxSimulationResultV1(
            simulation_id=simulation_id,
            correlation_id=request.correlation_id,
            evidence_hash=request.evidence_hash,
            issuer_id=request.issuer_id,
            authorization_reference=request.authorization_reference,
            requested_category=request.requested_category,
            affected_scope=request.requested_scope,
            estimated_impact=estimated_impact(request.requested_category),
            rollback_available=rollback_is_predicted(request.requested_category),
            risk_level=gateway.risk_level,
            confidence=0.0 if errors else gateway.confidence,
            status=status,
            timestamp=request.timestamp,
        )
        evidence_valid = not any(code.startswith(("EVIDENCE_", "ISSUER_")) for code in errors)
        audit_event, operational_event = sandbox_events(
            result,
            valid_evidence=evidence_valid,
        )
        telemetry_snapshot, telemetry_error = self._record_telemetry(operational_event)
        self.metrics.record(status)
        return SandboxEvaluationEnvelopeV1(
            simulation=result,
            environment=hypothetical_environment(request.requested_scope),
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


def _simulation_id(
    *,
    request: SandboxRequestV1,
    gateway: ToolGatewayDecisionResultV1,
    status: str,
    errors: tuple[str, ...],
) -> str:
    canonical = ":".join(
        (
            request.request_id,
            request.authorization_reference,
            request.requested_category.value,
            request.requested_scope.value,
            gateway.decision_id,
            status,
            ",".join(errors),
        )
    )
    return f"sandbox:{hashlib.sha256(canonical.encode()).hexdigest()[:32]}"
