"""Immutable result of a hypothetical plan traversal."""

from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import AfterValidator, Field

from ._base import require_timezone
from .decision import DecisionResultV1
from .execution_plan_result_v1 import ExecutionPlanStepV1

AwareDatetime = Annotated[datetime, AfterValidator(require_timezone)]
HashValue = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
SafeIdentifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")]


class SandboxExecutionStatusV1(str, Enum):
    SANDBOX_COMPLETED = "SANDBOX_COMPLETED"
    SANDBOX_FAILED = "SANDBOX_FAILED"
    SANDBOX_BLOCKED = "SANDBOX_BLOCKED"
    SANDBOX_INVALID = "SANDBOX_INVALID"


class SimulatedExecutionStepV1(DecisionResultV1):
    step_id: SafeIdentifier
    sequence: int = Field(ge=1, le=32)
    expected_state: SafeIdentifier
    completed: bool


class SandboxExecutionResultV1(DecisionResultV1):
    """Simulation evidence only; it cannot trigger plan execution."""

    execution_id: SafeIdentifier
    plan_id: SafeIdentifier
    correlation_id: SafeIdentifier
    evidence_hash: HashValue
    issuer_id: SafeIdentifier
    simulated_steps: tuple[SimulatedExecutionStepV1, ...]
    completed_steps: int = Field(ge=0)
    failed_steps: int = Field(ge=0)
    rollback_available: bool
    final_state: SandboxExecutionStatusV1
    confidence: float = Field(ge=0, le=100)
    timestamp: AwareDatetime
