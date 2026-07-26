"""Passive traversal engine with no system execution capability."""

from __future__ import annotations

import hashlib

from sentinel.contracts import (
    AuditEventV1,
    AuthorizationGrantV1,
    DecisionResultV1,
    EvidenceSignalV1,
    ExecutionPlanResultV1,
    PolicyEvaluationResultV1,
    SandboxExecutionResultV1,
    SandboxExecutionStatusV1,
)
from sentinel.evidence_integrity import EvidenceVerifier
from sentinel.operational_telemetry_hub import (
    OperationalEventV1,
    OperationalMetricSnapshotV1,
    OperationalTelemetryHub,
)

from .audit import execution_events
from .control import ExecutorSandboxControl
from .metrics import ExecutorSandboxMetrics, ExecutorSandboxMetricSnapshotV1
from .request import SandboxExecutionRequestV1
from .result import final_state
from .rollback import rollback_is_available
from .simulation import simulate_steps
from .validation import execution_validation_errors


class ExecutorSandboxEnvelopeV1(DecisionResultV1):
    result: SandboxExecutionResultV1
    validation_errors: tuple[str, ...]
    audit_event: AuditEventV1
    operational_event: OperationalEventV1
    telemetry_snapshot: OperationalMetricSnapshotV1 | None
    metrics: ExecutorSandboxMetricSnapshotV1
    telemetry_error: str | None = None


class PassiveExecutorSandboxV2:
    """Walks descriptive contracts only; no step is performed."""

    authority = False
    execution_requested = False

    def __init__(
        self,
        *,
        control: ExecutorSandboxControl,
        verifier: EvidenceVerifier,
        telemetry_hub: OperationalTelemetryHub,
        metrics: ExecutorSandboxMetrics | None = None,
    ) -> None:
        self.control = control
        self.verifier = verifier
        self.telemetry_hub = telemetry_hub
        self.metrics = metrics or ExecutorSandboxMetrics()

    def simulate(
        self,
        *,
        request: SandboxExecutionRequestV1,
        plan: ExecutionPlanResultV1,
        grant: AuthorizationGrantV1,
        policy: PolicyEvaluationResultV1,
        evidence: EvidenceSignalV1,
    ) -> ExecutorSandboxEnvelopeV1 | None:
        if not self.control.enabled:
            return None
        errors = execution_validation_errors(
            request=request,
            plan=plan,
            grant=grant,
            policy=policy,
            evidence=evidence,
            verifier=self.verifier,
        )
        state = final_state(
            errors=errors,
            plan_status=plan.status,
            policy_status=policy.policy_status,
        )
        blocked = state is not SandboxExecutionStatusV1.SANDBOX_COMPLETED
        steps = simulate_steps(plan, blocked=blocked)
        execution_id = _execution_id(request, state.value, errors)
        result = SandboxExecutionResultV1(
            execution_id=execution_id,
            plan_id=plan.plan_id,
            correlation_id=request.correlation_id,
            evidence_hash=request.evidence_hash,
            issuer_id=request.issuer_id,
            simulated_steps=steps,
            completed_steps=sum(step.completed for step in steps),
            failed_steps=sum(not step.completed for step in steps),
            rollback_available=rollback_is_available(plan),
            final_state=state,
            confidence=0.0 if errors else plan.confidence,
            timestamp=request.timestamp,
        )
        audit_event, operational_event = execution_events(result, valid_origin=not errors)
        telemetry_snapshot, telemetry_error = self._record_telemetry(operational_event)
        self.metrics.record(state)
        return ExecutorSandboxEnvelopeV1(
            result=result,
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


def _execution_id(
    request: SandboxExecutionRequestV1,
    state: str,
    errors: tuple[str, ...],
) -> str:
    canonical = ":".join((request.request_id, request.plan_id, state, ",".join(errors)))
    return f"sandbox-exec:{hashlib.sha256(canonical.encode()).hexdigest()[:32]}"
