"""Immutable descriptive plan emitted by passive Execution Planner V2."""

from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import AfterValidator, Field

from ._base import NonEmptyString, require_timezone
from .decision import DecisionResultV1
from .sandbox_simulation_result_v1 import SandboxCategoryV1
from .simulation_result_v1 import SimulationRiskLevelV1

AwareDatetime = Annotated[datetime, AfterValidator(require_timezone)]
HashValue = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
SafeIdentifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")]


class ExecutionPlanStatusV1(str, Enum):
    PLAN_CREATED = "PLAN_CREATED"
    PLAN_REVIEW_REQUIRED = "PLAN_REVIEW_REQUIRED"
    PLAN_BLOCKED = "PLAN_BLOCKED"
    PLAN_INVALID = "PLAN_INVALID"


class ExecutionPlanStepV1(DecisionResultV1):
    """Descriptive step without executable material."""

    step_id: SafeIdentifier
    sequence: int = Field(ge=1, le=32)
    description: NonEmptyString
    verification: NonEmptyString


class ExecutionPlanResultV1(DecisionResultV1):
    """Hypothetical plan only; it cannot be submitted for execution."""

    plan_id: SafeIdentifier
    correlation_id: SafeIdentifier
    evidence_hash: HashValue
    issuer_id: SafeIdentifier
    authorization_reference: SafeIdentifier
    action_category: SandboxCategoryV1
    steps: tuple[ExecutionPlanStepV1, ...] = Field(min_length=1, max_length=32)
    estimated_duration: int = Field(ge=0, le=86_400)
    rollback_strategy: NonEmptyString
    risk_level: SimulationRiskLevelV1
    confidence: float = Field(ge=0, le=100)
    status: ExecutionPlanStatusV1
    timestamp: AwareDatetime
