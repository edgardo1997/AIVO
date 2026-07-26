"""Opt-in versioned contracts for Sentinel's architectural migration.

Nothing in the existing runtime imports this package. Consumers must opt in
explicitly while legacy contracts remain unchanged.
"""

from .application_descriptor_v1 import (
    ApplicationDescriptorV1,
    ApplicationInstallStateV1,
    ApplicationLaunchTypeV1,
    ApplicationVerificationLevelV1,
)
from .audit import AuditEventV1
from .authority import NonAuthoritativeDecisionV1
from .authorization_grant_v1 import (
    AuthorizationGrantV1,
    AuthorizationScopeV1,
    AuthorizationStatusV1,
    AuthorizedStepV1,
)
from .decision import DecisionResultV1
from .consent_decision_result_v1 import (
    ConsentDecisionResultV1,
    ConsentDecisionValueV1,
)
from .evidence import EvidenceIntegrityStatusV1, EvidenceSignalV1
from .execution_plan_v2 import ExecutionPlanV2, ExecutionStepV2
from .health import HealthStateV1, HealthStatusV1
from .intent_v2 import IntentV2
from .identity_context_v1 import IdentityContextV1
from .launch_receipt_v1 import (
    LaunchErrorCodeV1,
    LaunchReceiptV1,
    LaunchStateV1,
)
from .limited_execution_receipt_v1 import (
    LimitedExecutionReceiptV1,
    LimitedExecutionStatusV1,
)
from .policy_context_v1 import PolicyContextV1
from .pending_consent_v1 import (
    PendingConsentStatusV1,
    PendingConsentV1,
)
from .policy_decision_v2 import (
    PolicyDecisionV2,
    PolicyDecisionV2Strict,
    PolicyDecisionValueV2,
)
from .policy_evaluation_result_v1 import (
    PolicyEvaluationResultV1,
    PolicyEvaluationStatusV1,
    PolicyViolationSeverityV1,
    PolicyViolationV1,
)
from .resolver_evidence_v1 import (
    ResolverEvidenceV1,
    ResolverVerificationStateV1,
)
from .sandbox_simulation_result_v1 import (
    SandboxCategoryV1,
    SandboxSimulationResultV1,
    SandboxSimulationStatusV1,
)
from .execution_boundary_decision_result_v1 import (
    ExecutionBoundaryDecisionResultV1,
    ExecutionBoundaryDecisionV1,
)
from .execution_plan_result_v1 import (
    ExecutionPlanResultV1,
    ExecutionPlanStatusV1,
    ExecutionPlanStepV1,
)
from .sandbox_execution_result_v1 import (
    SandboxExecutionResultV1,
    SandboxExecutionStatusV1,
    SimulatedExecutionStepV1,
)
from .isolation_context_result_v1 import (
    IsolationContextResultV1,
    IsolationLevelV1,
    IsolationResourceLimitsV1,
    IsolationStatusV1,
)
from .readiness import (
    ReadinessResultV1,
    ReadinessStateV1,
    ReadinessStateValueV1,
)
from .shadow_execution_trace_v1 import ShadowExecutionTraceV1
from .tool_gateway_decision_result_v1 import (
    ToolCategoryV1,
    ToolGatewayDecisionResultV1,
    ToolGatewayDecisionValueV1,
)
from .tool_catalog_v1 import (
    SignedToolCatalogV1,
    ToolParameterSpecV1,
    ToolParameterTypeV1,
    ToolSpecificationV1,
)
from .simulation_result_v1 import (
    RollbackComplexityV1,
    SimulationActionTypeV1,
    SimulationOutcomeV1,
    SimulationResultV1,
    SimulationRiskLevelV1,
)

__all__ = [
    "ApplicationDescriptorV1",
    "ApplicationInstallStateV1",
    "ApplicationLaunchTypeV1",
    "ApplicationVerificationLevelV1",
    "AuditEventV1",
    "AuthorizationGrantV1",
    "AuthorizationScopeV1",
    "AuthorizationStatusV1",
    "AuthorizedStepV1",
    "DecisionResultV1",
    "ConsentDecisionResultV1",
    "ConsentDecisionValueV1",
    "EvidenceIntegrityStatusV1",
    "EvidenceSignalV1",
    "ExecutionPlanV2",
    "ExecutionStepV2",
    "IntentV2",
    "IdentityContextV1",
    "HealthStateV1",
    "HealthStatusV1",
    "LaunchErrorCodeV1",
    "LaunchReceiptV1",
    "LaunchStateV1",
    "LimitedExecutionReceiptV1",
    "LimitedExecutionStatusV1",
    "PolicyContextV1",
    "PendingConsentStatusV1",
    "PendingConsentV1",
    "PolicyDecisionV2",
    "PolicyDecisionV2Strict",
    "PolicyDecisionValueV2",
    "PolicyEvaluationResultV1",
    "PolicyEvaluationStatusV1",
    "PolicyViolationSeverityV1",
    "PolicyViolationV1",
    "NonAuthoritativeDecisionV1",
    "ReadinessStateV1",
    "ReadinessStateValueV1",
    "ReadinessResultV1",
    "ResolverEvidenceV1",
    "ResolverVerificationStateV1",
    "SandboxCategoryV1",
    "SandboxSimulationResultV1",
    "SandboxSimulationStatusV1",
    "ExecutionBoundaryDecisionResultV1",
    "ExecutionBoundaryDecisionV1",
    "ExecutionPlanResultV1",
    "ExecutionPlanStatusV1",
    "ExecutionPlanStepV1",
    "SandboxExecutionResultV1",
    "SandboxExecutionStatusV1",
    "SimulatedExecutionStepV1",
    "IsolationContextResultV1",
    "IsolationLevelV1",
    "IsolationResourceLimitsV1",
    "IsolationStatusV1",
    "ShadowExecutionTraceV1",
    "ToolCategoryV1",
    "ToolGatewayDecisionResultV1",
    "ToolGatewayDecisionValueV1",
    "SignedToolCatalogV1",
    "ToolParameterSpecV1",
    "ToolParameterTypeV1",
    "ToolSpecificationV1",
    "RollbackComplexityV1",
    "SimulationActionTypeV1",
    "SimulationOutcomeV1",
    "SimulationResultV1",
    "SimulationRiskLevelV1",
]
