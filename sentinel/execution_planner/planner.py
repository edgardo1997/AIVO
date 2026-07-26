"""Completely passive structured plan generator."""

from __future__ import annotations

import hashlib

from sentinel.contracts import (
    AuditEventV1,
    AuthorizationGrantV1,
    DecisionResultV1,
    EvidenceSignalV1,
    ExecutionBoundaryDecisionResultV1,
    ExecutionPlanResultV1,
    PolicyEvaluationResultV1,
    SandboxSimulationResultV1,
)
from sentinel.evidence_integrity import EvidenceVerifier
from sentinel.operational_telemetry_hub import (
    OperationalEventV1,
    OperationalMetricSnapshotV1,
    OperationalTelemetryHub,
)

from .audit import planner_events
from .control import ExecutionPlannerControl
from .metrics import ExecutionPlannerMetrics, ExecutionPlannerMetricSnapshotV1
from .request import PlannerRequestV1
from .risk import plan_status
from .rollback import rollback_strategy
from .steps import descriptive_steps
from .validation import planner_validation_errors


class ExecutionPlannerEnvelopeV1(DecisionResultV1):
    plan: ExecutionPlanResultV1
    validation_errors: tuple[str, ...]
    audit_event: AuditEventV1
    operational_event: OperationalEventV1
    telemetry_snapshot: OperationalMetricSnapshotV1 | None
    metrics: ExecutionPlannerMetricSnapshotV1
    telemetry_error: str | None = None


class PassiveExecutionPlannerV2:
    """Creates descriptions only and has no execution surface."""

    authority = False
    execution_requested = False

    def __init__(
        self,
        *,
        control: ExecutionPlannerControl,
        verifier: EvidenceVerifier,
        telemetry_hub: OperationalTelemetryHub,
        metrics: ExecutionPlannerMetrics | None = None,
    ) -> None:
        self.control = control
        self.verifier = verifier
        self.telemetry_hub = telemetry_hub
        self.metrics = metrics or ExecutionPlannerMetrics()

    def create_plan(
        self,
        *,
        request: PlannerRequestV1,
        boundary: ExecutionBoundaryDecisionResultV1,
        grant: AuthorizationGrantV1,
        sandbox: SandboxSimulationResultV1,
        policy: PolicyEvaluationResultV1,
        evidence: EvidenceSignalV1,
    ) -> ExecutionPlannerEnvelopeV1 | None:
        if not self.control.enabled:
            return None
        errors = planner_validation_errors(
            request=request,
            boundary=boundary,
            grant=grant,
            sandbox=sandbox,
            policy=policy,
            evidence=evidence,
            verifier=self.verifier,
            now=request.timestamp,
        )
        selected = plan_status(
            errors=errors,
            boundary=boundary.decision,
            policy=policy.policy_status,
            sandbox=sandbox.status,
            risk=sandbox.risk_level,
        )
        steps = descriptive_steps(request.action_category)
        plan_id = _plan_id(request, selected.value, errors, steps)
        plan = ExecutionPlanResultV1(
            plan_id=plan_id,
            correlation_id=request.correlation_id,
            evidence_hash=request.evidence_hash,
            issuer_id=request.issuer_id,
            authorization_reference=request.authorization_reference,
            action_category=request.action_category,
            steps=steps,
            estimated_duration=len(steps) * 30,
            rollback_strategy=rollback_strategy(request.action_category),
            risk_level=sandbox.risk_level,
            confidence=0.0
            if errors
            else min(
                boundary.confidence,
                sandbox.confidence,
                policy.confidence,
            ),
            status=selected,
            timestamp=request.timestamp,
        )
        audit_event, operational_event = planner_events(plan, valid_origin=not errors)
        telemetry_snapshot, telemetry_error = self._record_telemetry(operational_event)
        self.metrics.record(selected)
        return ExecutionPlannerEnvelopeV1(
            plan=plan,
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


def _plan_id(request, status, errors, steps) -> str:
    canonical = ":".join(
        (
            request.request_id,
            request.boundary_reference,
            request.action_category.value,
            status,
            ",".join(errors),
            ",".join(step.step_id for step in steps),
        )
    )
    return f"plan-result:{hashlib.sha256(canonical.encode()).hexdigest()[:32]}"
