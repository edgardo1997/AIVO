"""Central immutable result for hypothetical, non-executing simulations."""

from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import AfterValidator, Field

from ._base import NonEmptyString, require_timezone
from .decision import DecisionResultV1

AwareDatetime = Annotated[datetime, AfterValidator(require_timezone)]
HashValue = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
SafeIdentifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")]


class SimulationActionTypeV1(str, Enum):
    DELETE_FILE = "DELETE_FILE"
    INSTALL_APPLICATION = "INSTALL_APPLICATION"
    STOP_PROCESS = "STOP_PROCESS"
    MODIFY_CONFIGURATION = "MODIFY_CONFIGURATION"
    SYSTEM_INFORMATION = "SYSTEM_INFORMATION"
    FILE_METADATA = "FILE_METADATA"
    APPLICATION_LAUNCH = "APPLICATION_LAUNCH"


class SimulationRiskLevelV1(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SimulationOutcomeV1(str, Enum):
    SIMULATION_SAFE = "SIMULATION_SAFE"
    SIMULATION_WARNING = "SIMULATION_WARNING"
    SIMULATION_HIGH_RISK = "SIMULATION_HIGH_RISK"
    SIMULATION_BLOCKED = "SIMULATION_BLOCKED"


class RollbackComplexityV1(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class SimulationResultV1(DecisionResultV1):
    """A prediction only; it can never authorize or request execution."""

    simulation_id: SafeIdentifier
    correlation_id: SafeIdentifier
    evidence_hash: HashValue
    issuer_id: SafeIdentifier
    timestamp: AwareDatetime
    action_type: SimulationActionTypeV1
    target_class: SafeIdentifier
    result_type: SimulationOutcomeV1
    risk_level: SimulationRiskLevelV1
    impact_summary: NonEmptyString
    dependencies: tuple[SafeIdentifier, ...]
    rollback_available: bool
    rollback_complexity: RollbackComplexityV1
    estimated_effect: NonEmptyString
    confirmation_required: bool
    confidence: float = Field(ge=0, le=100)
