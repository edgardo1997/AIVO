"""Central immutable result for passive V2 policy evaluation."""

from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import AfterValidator, Field

from ._base import NonEmptyString, require_timezone
from .decision import DecisionResultV1
from .simulation_result_v1 import (
    SimulationActionTypeV1,
    SimulationRiskLevelV1,
)

AwareDatetime = Annotated[datetime, AfterValidator(require_timezone)]
HashValue = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
SafeIdentifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")]


class PolicyEvaluationStatusV1(str, Enum):
    POLICY_ALLOWED = "POLICY_ALLOWED"
    POLICY_REVIEW_REQUIRED = "POLICY_REVIEW_REQUIRED"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    POLICY_UNKNOWN = "POLICY_UNKNOWN"


class PolicyViolationSeverityV1(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class PolicyViolationV1(DecisionResultV1):
    rule_id: SafeIdentifier
    severity: PolicyViolationSeverityV1
    description: NonEmptyString
    reason: NonEmptyString


class PolicyEvaluationResultV1(DecisionResultV1):
    """Policy compatibility only; never an authorization."""

    policy_id: SafeIdentifier
    correlation_id: SafeIdentifier
    evidence_hash: HashValue
    issuer_id: SafeIdentifier
    timestamp: AwareDatetime
    action_type: SimulationActionTypeV1
    risk_level: SimulationRiskLevelV1
    policy_status: PolicyEvaluationStatusV1
    violations: tuple[PolicyViolationV1, ...]
    requirements: tuple[SafeIdentifier, ...]
    confidence: float = Field(ge=0, le=100)
