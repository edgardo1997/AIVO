"""Contract-only orchestration of the existing passive V2 stages."""

from __future__ import annotations

import hashlib

from sentinel.authorization_manager import (
    AuthorizationManagerControl,
    AuthorizationManagerV2,
)
from sentinel.consent_manager import ConsentManagerControl, ConsentManagerV2
from sentinel.contracts import (
    AuthorizationStatusV1,
    ConsentDecisionValueV1,
    ExecutionBoundaryDecisionV1,
    ExecutionPlanStatusV1,
    IsolationStatusV1,
    PolicyEvaluationStatusV1,
    SandboxExecutionStatusV1,
    SandboxSimulationStatusV1,
    ToolGatewayDecisionValueV1,
)
from sentinel.evidence_integrity import EvidenceVerifier
from sentinel.execution_boundary import (
    ExecutionBoundaryControl,
    ExecutionRequestV1,
    PassiveExecutionBoundaryV2,
)
from sentinel.execution_planner import (
    ExecutionPlannerControl,
    PassiveExecutionPlannerV2,
    PlannerRequestV1,
)
from sentinel.executor_sandbox import (
    ExecutorSandboxControl,
    PassiveExecutorSandboxV2,
    SandboxExecutionRequestV1,
)
from sentinel.operational_telemetry_hub import OperationalTelemetryHub
from sentinel.policy_engine import PassivePolicyEngine, PolicyEngineControl
from sentinel.runtime_isolation import (
    IsolationRequestV1,
    PassiveRuntimeIsolationV2,
    RuntimeIsolationControl,
)
from sentinel.sandbox_engine import (
    PassiveSandboxEngineV2,
    SandboxEngineControl,
    SandboxRequestV1,
)
from sentinel.tool_gateway import (
    PassiveToolGatewayV2,
    ToolGatewayControl,
    ToolRequestV1,
)
from sentinel.tool_gateway.catalog import default_tool_id

from .control import UnifiedPipelineControl
from .models import (
    UnifiedPipelineRequestV1,
    UnifiedPipelineResultV1,
    UnifiedPipelineStatusV1,
)


class PassiveUnifiedPipelineV2:
    """Links passive contracts and never exposes an execution method."""

    authority = False
    execution_requested = False

    def __init__(
        self,
        *,
        control: UnifiedPipelineControl,
        verifier: EvidenceVerifier,
        telemetry_hub: OperationalTelemetryHub,
    ) -> None:
        self.control = control
        self.verifier = verifier
        self.telemetry_hub = telemetry_hub
        self.authorization_manager = AuthorizationManagerV2(
            control=AuthorizationManagerControl(enabled=True),
            verifier=self.verifier,
            telemetry_hub=self.telemetry_hub,
        )

    def evaluate(
        self,
        request: UnifiedPipelineRequestV1,
        *,
        consent_decision: ConsentDecisionValueV1 | None = None,
        human_actor: str | None = None,
    ) -> UnifiedPipelineResultV1:
        """Evaluate the full passive chain, stopping at the first unsafe stage."""
        if not self.control.enabled:
            return self._result(
                request,
                status=UnifiedPipelineStatusV1.DISABLED,
                failed_stage="control",
                errors=("PIPELINE_DISABLED",),
            )
        if self.telemetry_hub.aggregator is None or self.telemetry_hub.storage is None:
            return self._result(
                request,
                status=UnifiedPipelineStatusV1.INVALID,
                failed_stage="telemetry",
                errors=("TELEMETRY_REQUIRED",),
            )

        completed: list[str] = ["intent"]
        values: dict[str, object] = {}
        current_stage = "policy"
        try:
            policy_engine = PassivePolicyEngine(
                control=PolicyEngineControl(enabled=True),
                telemetry_hub=self.telemetry_hub,
            )
            policy_envelope = policy_engine.evaluate(
                decision=request.decision,
                recommendation=request.recommendation,
                simulation=request.simulation,
                evidence=request.evidence,
                trust=request.trust,
                readiness=request.readiness,
                health=request.health,
            )
            if policy_envelope is None:
                return self._closed(request, completed, "policy", "NO_RESULT")
            values["policy_envelope"] = policy_envelope
            values["policy"] = policy_envelope.evaluation
            telemetry_error = self._telemetry_error(policy_envelope)
            if telemetry_error:
                return self._closed(request, completed, "policy", telemetry_error, **values)
            completed.append("policy")
            if policy_envelope.evaluation.policy_status in {
                PolicyEvaluationStatusV1.POLICY_BLOCKED,
                PolicyEvaluationStatusV1.POLICY_UNKNOWN,
            }:
                return self._closed(request, completed, "policy", "POLICY_NOT_COMPATIBLE", **values)

            current_stage = "consent"
            consent_manager = ConsentManagerV2(
                control=ConsentManagerControl(enabled=True),
                verifier=self.verifier,
                telemetry_hub=self.telemetry_hub,
            )
            pending_operation = consent_manager.request(
                policy=policy_envelope.evaluation,
                simulation=request.simulation,
                recommendation=request.recommendation,
                evidence=request.evidence,
                readiness=request.readiness,
                expiration_time=request.consent_expires_at,
                now=request.timestamp,
            )
            if pending_operation is None:
                return self._closed(request, completed, "consent", "NO_RESULT", **values)
            values["consent"] = pending_operation.consent
            telemetry_error = self._telemetry_error(pending_operation)
            if telemetry_error:
                return self._closed(request, completed, "consent", telemetry_error, **values)
            completed.append("consent")
            if consent_decision is None:
                return self._result(
                    request,
                    status=UnifiedPipelineStatusV1.AWAITING_CONSENT,
                    completed=completed,
                    **values,
                )
            if not human_actor or not human_actor.startswith("human:"):
                return self._closed(
                    request,
                    completed,
                    "consent",
                    "EXPLICIT_HUMAN_ACTOR_REQUIRED",
                    **values,
                )
            decided_operation = consent_manager.decide(
                pending_operation.consent.consent_id,
                decision=consent_decision,
                decision_source=human_actor,
                now=request.timestamp,
            )
            values["consent"] = decided_operation.consent
            telemetry_error = self._telemetry_error(decided_operation)
            if telemetry_error:
                return self._closed(request, completed, "consent", telemetry_error, **values)
            if decided_operation.consent.decision is not ConsentDecisionValueV1.CONSENT_GRANTED:
                return self._closed(request, completed, "consent", "CONSENT_NOT_GRANTED", **values)

            current_stage = "authorization"
            catalog_tool_id = default_tool_id(request.tool_category)
            authorization_plan_id = self._id(request, "authorization-plan")
            authorization_step_id = self._id(request, "authorization-step")
            authorization_operation = self.authorization_manager.issue_limited_from_consent(
                consent=decided_operation.consent,
                policy=policy_envelope.evaluation,
                evidence=request.evidence,
                scope=request.authorization_scope,
                params_hash=request.parameters_hash,
                plan_id=authorization_plan_id,
                step_id=authorization_step_id,
                tool_id=catalog_tool_id,
                expires_at=request.authorization_expires_at,
                now=request.timestamp,
            )
            if authorization_operation is None:
                return self._closed(request, completed, "authorization", "NO_RESULT", **values)
            values["authorization"] = authorization_operation.grant
            telemetry_error = self._telemetry_error(authorization_operation)
            if telemetry_error:
                return self._closed(request, completed, "authorization", telemetry_error, **values)
            completed.append("authorization")
            grant = authorization_operation.grant
            if grant.status is not AuthorizationStatusV1.AUTHORIZED_LIMITED:
                return self._closed(request, completed, "authorization", "GRANT_NOT_LIMITED", **values)

            current_stage = "tool_gateway"
            tool_request = ToolRequestV1(
                request_id=self._id(request, "tool-request"),
                correlation_id=request.correlation_id,
                evidence_hash=request.evidence.payload_hash,
                issuer_id=request.evidence.issuer_id,
                authorization_reference=grant.grant_id,
                plan_id=grant.plan_id,
                step_id=grant.authorized_steps[0].step_id,
                tool_id=catalog_tool_id,
                tool_version="1.0.0",
                requested_tool_category=request.tool_category,
                requested_scope=request.authorization_scope,
                parameters=(),
                params_hash=request.parameters_hash,
                timestamp=request.timestamp,
            )
            gateway_envelope = PassiveToolGatewayV2(
                control=ToolGatewayControl(enabled=True),
                verifier=self.verifier,
                telemetry_hub=self.telemetry_hub,
            ).evaluate(
                request=tool_request,
                grant=grant,
                consent=decided_operation.consent,
                evidence=request.evidence,
                policy=policy_envelope.evaluation,
                now=request.timestamp,
            )
            if gateway_envelope is None:
                return self._closed(request, completed, "tool_gateway", "NO_RESULT", **values)
            values["gateway"] = gateway_envelope.decision
            telemetry_error = self._telemetry_error(gateway_envelope)
            if telemetry_error:
                return self._closed(request, completed, "tool_gateway", telemetry_error, **values)
            completed.append("tool_gateway")
            if gateway_envelope.decision.decision is not ToolGatewayDecisionValueV1.TOOL_ALLOWED:
                return self._closed(request, completed, "tool_gateway", "TOOL_NOT_ALLOWED", **values)

            current_stage = "sandbox"
            sandbox_request = SandboxRequestV1(
                request_id=self._id(request, "sandbox-request"),
                correlation_id=request.correlation_id,
                evidence_hash=request.evidence.payload_hash,
                issuer_id=request.evidence.issuer_id,
                authorization_reference=grant.grant_id,
                requested_category=request.sandbox_category,
                requested_scope=request.authorization_scope,
                timestamp=request.timestamp,
            )
            sandbox_envelope = PassiveSandboxEngineV2(
                control=SandboxEngineControl(enabled=True),
                verifier=self.verifier,
                telemetry_hub=self.telemetry_hub,
            ).simulate(
                request=sandbox_request,
                gateway=gateway_envelope.decision,
                grant=grant,
                evidence=request.evidence,
            )
            if sandbox_envelope is None:
                return self._closed(request, completed, "sandbox", "NO_RESULT", **values)
            values["sandbox"] = sandbox_envelope.simulation
            telemetry_error = self._telemetry_error(sandbox_envelope)
            if telemetry_error:
                return self._closed(request, completed, "sandbox", telemetry_error, **values)
            completed.append("sandbox")
            if sandbox_envelope.simulation.status in {
                SandboxSimulationStatusV1.SIMULATION_BLOCKED,
                SandboxSimulationStatusV1.SIMULATION_HIGH_RISK,
            }:
                return self._closed(request, completed, "sandbox", "SANDBOX_NOT_SAFE", **values)

            current_stage = "boundary"
            boundary_request = ExecutionRequestV1(
                request_id=self._id(request, "boundary-request"),
                correlation_id=request.correlation_id,
                evidence_hash=request.evidence.payload_hash,
                issuer_id=request.evidence.issuer_id,
                authorization_reference=grant.grant_id,
                gateway_reference=gateway_envelope.decision.decision_id,
                simulation_reference=sandbox_envelope.simulation.simulation_id,
                policy_reference=policy_envelope.evaluation.policy_id,
                action_category=request.sandbox_category,
                scope=request.authorization_scope,
                simulation_status=sandbox_envelope.simulation.status,
                timestamp=request.timestamp,
            )
            boundary_envelope = PassiveExecutionBoundaryV2(
                control=ExecutionBoundaryControl(enabled=True),
                verifier=self.verifier,
                telemetry_hub=self.telemetry_hub,
            ).evaluate(
                request=boundary_request,
                grant=grant,
                gateway=gateway_envelope.decision,
                simulation=sandbox_envelope.simulation,
                policy=policy_envelope.evaluation,
                evidence=request.evidence,
            )
            if boundary_envelope is None:
                return self._closed(request, completed, "boundary", "NO_RESULT", **values)
            values["boundary"] = boundary_envelope.decision
            telemetry_error = self._telemetry_error(boundary_envelope)
            if telemetry_error:
                return self._closed(request, completed, "boundary", telemetry_error, **values)
            completed.append("boundary")
            if boundary_envelope.decision.decision in {
                ExecutionBoundaryDecisionV1.EXECUTION_BLOCKED,
                ExecutionBoundaryDecisionV1.EXECUTION_INVALID,
            }:
                return self._closed(request, completed, "boundary", "BOUNDARY_NOT_READY", **values)

            current_stage = "planner"
            planner_request = PlannerRequestV1(
                request_id=self._id(request, "planner-request"),
                correlation_id=request.correlation_id,
                evidence_hash=request.evidence.payload_hash,
                issuer_id=request.evidence.issuer_id,
                authorization_reference=grant.grant_id,
                boundary_reference=boundary_envelope.decision.decision_id,
                simulation_reference=sandbox_envelope.simulation.simulation_id,
                policy_reference=policy_envelope.evaluation.policy_id,
                action_category=request.sandbox_category,
                scope=request.authorization_scope,
                timestamp=request.timestamp,
            )
            planner_envelope = PassiveExecutionPlannerV2(
                control=ExecutionPlannerControl(enabled=True),
                verifier=self.verifier,
                telemetry_hub=self.telemetry_hub,
            ).create_plan(
                request=planner_request,
                boundary=boundary_envelope.decision,
                grant=grant,
                sandbox=sandbox_envelope.simulation,
                policy=policy_envelope.evaluation,
                evidence=request.evidence,
            )
            if planner_envelope is None:
                return self._closed(request, completed, "planner", "NO_RESULT", **values)
            values["plan"] = planner_envelope.plan
            telemetry_error = self._telemetry_error(planner_envelope)
            if telemetry_error:
                return self._closed(request, completed, "planner", telemetry_error, **values)
            completed.append("planner")
            if planner_envelope.plan.status in {
                ExecutionPlanStatusV1.PLAN_BLOCKED,
                ExecutionPlanStatusV1.PLAN_INVALID,
            }:
                return self._closed(request, completed, "planner", "PLAN_NOT_VALID", **values)

            current_stage = "executor_sandbox"
            execution_request = SandboxExecutionRequestV1(
                request_id=self._id(request, "sandbox-execution-request"),
                plan_id=planner_envelope.plan.plan_id,
                correlation_id=request.correlation_id,
                evidence_hash=request.evidence.payload_hash,
                issuer_id=request.evidence.issuer_id,
                authorization_reference=grant.grant_id,
                policy_reference=policy_envelope.evaluation.policy_id,
                scope=request.authorization_scope,
                timestamp=request.timestamp,
                valid_until=request.authorization_expires_at,
            )
            execution_envelope = PassiveExecutorSandboxV2(
                control=ExecutorSandboxControl(enabled=True),
                verifier=self.verifier,
                telemetry_hub=self.telemetry_hub,
            ).simulate(
                request=execution_request,
                plan=planner_envelope.plan,
                grant=grant,
                policy=policy_envelope.evaluation,
                evidence=request.evidence,
            )
            if execution_envelope is None:
                return self._closed(request, completed, "executor_sandbox", "NO_RESULT", **values)
            values["sandbox_execution"] = execution_envelope.result
            telemetry_error = self._telemetry_error(execution_envelope)
            if telemetry_error:
                return self._closed(request, completed, "executor_sandbox", telemetry_error, **values)
            completed.append("executor_sandbox")
            if execution_envelope.result.final_state is not SandboxExecutionStatusV1.SANDBOX_COMPLETED:
                return self._closed(
                    request,
                    completed,
                    "executor_sandbox",
                    "SANDBOX_EXECUTION_NOT_COMPLETED",
                    **values,
                )

            current_stage = "isolation"
            isolation_request = IsolationRequestV1(
                request_id=self._id(request, "isolation-request"),
                execution_reference=execution_envelope.result.execution_id,
                plan_reference=planner_envelope.plan.plan_id,
                authorization_reference=grant.grant_id,
                correlation_id=request.correlation_id,
                evidence_hash=request.evidence.payload_hash,
                issuer_id=request.evidence.issuer_id,
                requested_scope=request.authorization_scope,
                timestamp=request.timestamp,
            )
            isolation_envelope = PassiveRuntimeIsolationV2(
                control=RuntimeIsolationControl(enabled=True),
                verifier=self.verifier,
                telemetry_hub=self.telemetry_hub,
            ).evaluate(
                request=isolation_request,
                execution=execution_envelope.result,
                plan=planner_envelope.plan,
                grant=grant,
                evidence=request.evidence,
            )
            if isolation_envelope is None:
                return self._closed(request, completed, "isolation", "NO_RESULT", **values)
            values["isolation"] = isolation_envelope.context
            telemetry_error = self._telemetry_error(isolation_envelope)
            if telemetry_error:
                return self._closed(request, completed, "isolation", telemetry_error, **values)
            completed.append("isolation")
            if isolation_envelope.context.status not in {
                IsolationStatusV1.ISOLATION_READY,
                IsolationStatusV1.ISOLATION_RESTRICTED,
            }:
                return self._closed(request, completed, "isolation", "ISOLATION_NOT_READY", **values)
            current_stage = "authorization"
            consumed_operation = self.authorization_manager.consume(
                grant.grant_id,
                params_hash=request.parameters_hash,
                now=request.timestamp,
            )
            values["authorization"] = consumed_operation.grant
            return self._result(
                request,
                status=UnifiedPipelineStatusV1.COMPLETED,
                completed=completed,
                **values,
            )
        except Exception as exc:
            return self._closed(
                request,
                completed,
                current_stage,
                type(exc).__name__,
                **values,
            )

    @staticmethod
    def _telemetry_error(envelope: object) -> str | None:
        return getattr(envelope, "telemetry_error", None)

    @staticmethod
    def _id(request: UnifiedPipelineRequestV1, prefix: str) -> str:
        digest = hashlib.sha256(
            (f"{request.correlation_id}:{request.evidence.payload_hash}:{prefix}").encode("utf-8")
        ).hexdigest()[:32]
        return f"{prefix}:{digest}"

    def _closed(
        self,
        request: UnifiedPipelineRequestV1,
        completed: list[str],
        stage: str,
        error: str,
        **values,
    ) -> UnifiedPipelineResultV1:
        return self._result(
            request,
            status=UnifiedPipelineStatusV1.BLOCKED,
            completed=completed,
            failed_stage=stage,
            errors=(error,),
            **values,
        )

    @staticmethod
    def _result(
        request: UnifiedPipelineRequestV1,
        *,
        status: UnifiedPipelineStatusV1,
        completed: list[str] | tuple[str, ...] = (),
        failed_stage: str | None = None,
        errors: tuple[str, ...] = (),
        **values,
    ) -> UnifiedPipelineResultV1:
        return UnifiedPipelineResultV1(
            correlation_id=request.correlation_id,
            evidence_hash=request.evidence.payload_hash,
            issuer_id=request.evidence.issuer_id,
            timestamp=request.timestamp,
            status=status,
            completed_stages=tuple(completed),
            failed_stage=failed_stage,
            errors=errors,
            **values,
        )
