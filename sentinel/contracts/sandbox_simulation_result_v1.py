"""Central immutable result for passive sandbox simulation."""

from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import AfterValidator, Field

from ._base import NonEmptyString, require_timezone
from .authorization_grant_v1 import AuthorizationScopeV1
from .decision import DecisionResultV1
from .simulation_result_v1 import SimulationRiskLevelV1

AwareDatetime = Annotated[datetime, AfterValidator(require_timezone)]
HashValue = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
SafeIdentifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")]


class SandboxCategoryV1(str, Enum):
    FILE_OPERATION = "FILE_OPERATION"
    PROCESS_OPERATION = "PROCESS_OPERATION"
    SYSTEM_CONFIGURATION = "SYSTEM_CONFIGURATION"
    APPLICATION_CHANGE = "APPLICATION_CHANGE"
    DATA_OPERATION = "DATA_OPERATION"


class SandboxSimulationStatusV1(str, Enum):
    SIMULATION_SAFE = "SIMULATION_SAFE"
    SIMULATION_WARNING = "SIMULATION_WARNING"
    SIMULATION_HIGH_RISK = "SIMULATION_HIGH_RISK"
    SIMULATION_BLOCKED = "SIMULATION_BLOCKED"


class SandboxSimulationResultV1(DecisionResultV1):
    """Hypothetical impact only; never a runnable sandbox instruction."""

    simulation_id: SafeIdentifier
    correlation_id: SafeIdentifier
    evidence_hash: HashValue
    issuer_id: SafeIdentifier
    authorization_reference: SafeIdentifier
    requested_category: SandboxCategoryV1
    affected_scope: AuthorizationScopeV1
    estimated_impact: NonEmptyString
    rollback_available: bool
    risk_level: SimulationRiskLevelV1
    confidence: float = Field(ge=0, le=100)
    status: SandboxSimulationStatusV1
    timestamp: AwareDatetime
