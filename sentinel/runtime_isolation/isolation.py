"""Passive runtime-isolation context coordinator."""

from __future__ import annotations

import hashlib

from sentinel.contracts import (
    AuditEventV1,
    AuthorizationGrantV1,
    DecisionResultV1,
    EvidenceSignalV1,
    ExecutionPlanResultV1,
    IsolationContextResultV1,
    SandboxExecutionResultV1,
)
from sentinel.evidence_integrity import EvidenceVerifier
from sentinel.operational_telemetry_hub import (
    OperationalEventV1,
    OperationalMetricSnapshotV1,
    OperationalTelemetryHub,
)

from .audit import isolation_events
from .context import isolation_outcome
from .control import RuntimeIsolationControl
from .limits import descriptive_limits
from .metrics import RuntimeIsolationMetrics, RuntimeIsolationMetricSnapshotV1
from .request import IsolationRequestV1
from .security import ALLOWED_CAPABILITIES, BLOCKED_CAPABILITIES
from .validation import isolation_validation_errors


class RuntimeIsolationEnvelopeV1(DecisionResultV1):
    context: IsolationContextResultV1
    validation_errors: tuple[str, ...]
    audit_event: AuditEventV1
    operational_event: OperationalEventV1
    telemetry_snapshot: OperationalMetricSnapshotV1 | None
    metrics: RuntimeIsolationMetricSnapshotV1
    telemetry_error: str | None = None


class PassiveRuntimeIsolationV2:
    """Describes isolation and never provisions a runtime."""

    authority = False
    execution_requested = False

    def __init__(
        self,
        *,
        control: RuntimeIsolationControl,
        verifier: EvidenceVerifier,
        telemetry_hub: OperationalTelemetryHub,
        metrics: RuntimeIsolationMetrics | None = None,
    ) -> None:
        self.control = control
        self.verifier = verifier
        self.telemetry_hub = telemetry_hub
        self.metrics = metrics or RuntimeIsolationMetrics()

    def evaluate(
        self,
        *,
        request: IsolationRequestV1,
        execution: SandboxExecutionResultV1,
        plan: ExecutionPlanResultV1,
        grant: AuthorizationGrantV1,
        evidence: EvidenceSignalV1,
    ) -> RuntimeIsolationEnvelopeV1 | None:
        if not self.control.enabled:
            return None
        errors = isolation_validation_errors(
            request=request,
            execution=execution,
            plan=plan,
            grant=grant,
            evidence=evidence,
            verifier=self.verifier,
        )
        level, status = isolation_outcome(errors=errors, sandbox_state=execution.final_state)
        isolation_id = _isolation_id(request, status.value, errors)
        context = IsolationContextResultV1(
            isolation_id=isolation_id,
            execution_reference=request.execution_reference,
            correlation_id=request.correlation_id,
            evidence_hash=request.evidence_hash,
            issuer_id=request.issuer_id,
            isolation_level=level,
            allowed_capabilities=(() if errors else ALLOWED_CAPABILITIES),
            blocked_capabilities=BLOCKED_CAPABILITIES,
            resource_limits=descriptive_limits(len(execution.simulated_steps)),
            status=status,
            confidence=0.0 if errors else execution.confidence,
            timestamp=request.timestamp,
        )
        audit_event, operational_event = isolation_events(context, valid_origin=not errors)
        telemetry_snapshot, telemetry_error = self._record_telemetry(operational_event)
        self.metrics.record(status)
        return RuntimeIsolationEnvelopeV1(
            context=context,
            validation_errors=errors,
            audit_event=audit_event,
            operational_event=operational_event,
            telemetry_snapshot=telemetry_snapshot,
            metrics=self.metrics.snapshot(),
            telemetry_error=telemetry_error,
        )

    def _record_telemetry(self, event: OperationalEventV1) -> tuple[OperationalMetricSnapshotV1 | None, str | None]:
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


def _isolation_id(
    request: IsolationRequestV1,
    status: str,
    errors: tuple[str, ...],
) -> str:
    canonical = ":".join((request.request_id, request.execution_reference, status, ",".join(errors)))
    return f"isolation:{hashlib.sha256(canonical.encode()).hexdigest()[:32]}"
