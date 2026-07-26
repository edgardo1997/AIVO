"""Immutable passive decision emitted by Execution Boundary V2."""

from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import AfterValidator, Field

from ._base import require_timezone
from .authorization_grant_v1 import AuthorizationScopeV1
from .decision import DecisionResultV1
from .sandbox_simulation_result_v1 import (
    SandboxCategoryV1,
    SandboxSimulationStatusV1,
)
from .simulation_result_v1 import SimulationRiskLevelV1

AwareDatetime = Annotated[datetime, AfterValidator(require_timezone)]
HashValue = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
SafeIdentifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")]


class ExecutionBoundaryDecisionV1(str, Enum):
    EXECUTION_BLOCKED = "EXECUTION_BLOCKED"
    EXECUTION_REVIEW_REQUIRED = "EXECUTION_REVIEW_REQUIRED"
    EXECUTION_READY = "EXECUTION_READY"
    EXECUTION_INVALID = "EXECUTION_INVALID"


class ExecutionBoundaryDecisionResultV1(DecisionResultV1):
    """Contractual readiness only; EXECUTION_READY cannot execute anything."""

    decision_id: SafeIdentifier
    correlation_id: SafeIdentifier
    evidence_hash: HashValue
    issuer_id: SafeIdentifier
    authorization_reference: SafeIdentifier
    gateway_reference: SafeIdentifier
    simulation_reference: SafeIdentifier
    policy_reference: SafeIdentifier
    action_category: SandboxCategoryV1
    scope: AuthorizationScopeV1
    simulation_status: SandboxSimulationStatusV1
    risk_level: SimulationRiskLevelV1
    decision: ExecutionBoundaryDecisionV1
    confidence: float = Field(ge=0, le=100)
    timestamp: AwareDatetime
