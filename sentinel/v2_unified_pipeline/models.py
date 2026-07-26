"""Input and result contracts for the passive unified V2 pipeline."""

from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import AfterValidator, Field, model_validator

from sentinel.contracts import (
    AuthorizationGrantV1,
    AuthorizationScopeV1,
    ConsentDecisionResultV1,
    DecisionResultV1,
    EvidenceSignalV1,
    HealthStatusV1,
    IntentV2,
    IsolationContextResultV1,
    PolicyEvaluationResultV1,
    ReadinessResultV1,
    SandboxCategoryV1,
    SandboxExecutionResultV1,
    SandboxSimulationResultV1,
    SimulationResultV1,
    ToolCategoryV1,
    ToolGatewayDecisionResultV1,
    ExecutionBoundaryDecisionResultV1,
    ExecutionPlanResultV1,
)
from sentinel.contracts._base import require_timezone
from sentinel.policy_engine import PolicyEvaluationEnvelopeV1
from sentinel.recommendation_engine import RecommendationResultV1
from sentinel.v2_trust_evaluation import TrustEvaluationResultV1

AwareDatetime = Annotated[datetime, AfterValidator(require_timezone)]
HashValue = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
SafeIdentifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")]


class UnifiedPipelineStatusV1(str, Enum):
    DISABLED = "DISABLED"
    AWAITING_CONSENT = "AWAITING_CONSENT"
    AWAITING_AUTHORIZATION = "AWAITING_AUTHORIZATION"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    INVALID = "INVALID"


class UnifiedPipelineRequestV1(DecisionResultV1):
    """Sanitized contract bundle needed by the existing passive stages."""

    correlation_id: SafeIdentifier
    intent: IntentV2
    decision: DecisionResultV1
    recommendation: RecommendationResultV1
    simulation: SimulationResultV1
    evidence: EvidenceSignalV1
    trust: TrustEvaluationResultV1
    readiness: ReadinessResultV1
    health: HealthStatusV1
    authorization_scope: AuthorizationScopeV1
    parameters_hash: HashValue
    tool_category: ToolCategoryV1
    sandbox_category: SandboxCategoryV1
    timestamp: AwareDatetime
    consent_expires_at: AwareDatetime
    authorization_expires_at: AwareDatetime

    @model_validator(mode="after")
    def validate_shared_origin(self):
        if self.correlation_id != self.evidence.correlation_id:
            raise ValueError("pipeline correlation does not match evidence")
        if self.consent_expires_at <= self.timestamp:
            raise ValueError("consent expiration must follow pipeline time")
        if self.authorization_expires_at <= self.timestamp:
            raise ValueError("authorization expiration must follow pipeline time")
        if self.authorization_expires_at > self.consent_expires_at:
            raise ValueError("authorization cannot outlive consent")
        return self


class UnifiedPipelineResultV1(DecisionResultV1):
    """Non-authoritative snapshot of the furthest completed passive stage."""

    correlation_id: SafeIdentifier
    evidence_hash: HashValue
    issuer_id: SafeIdentifier
    timestamp: AwareDatetime
    status: UnifiedPipelineStatusV1
    completed_stages: tuple[str, ...] = ()
    failed_stage: str | None = None
    errors: tuple[str, ...] = ()
    policy: PolicyEvaluationResultV1 | None = None
    consent: ConsentDecisionResultV1 | None = None
    authorization: AuthorizationGrantV1 | None = None
    gateway: ToolGatewayDecisionResultV1 | None = None
    sandbox: SandboxSimulationResultV1 | None = None
    boundary: ExecutionBoundaryDecisionResultV1 | None = None
    plan: ExecutionPlanResultV1 | None = None
    sandbox_execution: SandboxExecutionResultV1 | None = None
    isolation: IsolationContextResultV1 | None = None
    policy_envelope: PolicyEvaluationEnvelopeV1 | None = None
