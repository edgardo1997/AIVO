"""Central immutable result for passive Tool Gateway V2 evaluation."""

from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import AfterValidator, Field

from ._base import require_timezone
from .authorization_grant_v1 import AuthorizationScopeV1
from .decision import DecisionResultV1
from .simulation_result_v1 import SimulationRiskLevelV1

AwareDatetime = Annotated[datetime, AfterValidator(require_timezone)]
HashValue = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
SafeIdentifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")]


class ToolCategoryV1(str, Enum):
    FILE_READ = "FILE_READ"
    FILE_ANALYSIS = "FILE_ANALYSIS"
    SYSTEM_INFORMATION = "SYSTEM_INFORMATION"
    PROCESS_INFORMATION = "PROCESS_INFORMATION"
    APPLICATION_LAUNCH = "APPLICATION_LAUNCH"
    USER_APPROVED_CHANGE = "USER_APPROVED_CHANGE"


class ToolGatewayDecisionValueV1(str, Enum):
    TOOL_ALLOWED = "TOOL_ALLOWED"
    TOOL_BLOCKED = "TOOL_BLOCKED"
    TOOL_REQUIRES_REVIEW = "TOOL_REQUIRES_REVIEW"
    TOOL_UNKNOWN = "TOOL_UNKNOWN"


class ToolGatewayDecisionResultV1(DecisionResultV1):
    """Evaluation only; TOOL_ALLOWED does not authorize execution."""

    decision_id: SafeIdentifier
    correlation_id: SafeIdentifier
    evidence_hash: HashValue
    issuer_id: SafeIdentifier
    authorization_reference: SafeIdentifier
    plan_id: SafeIdentifier
    step_id: SafeIdentifier
    tool_id: SafeIdentifier
    tool_version: SafeIdentifier
    params_hash: HashValue
    catalog_hash: HashValue
    requested_tool_category: ToolCategoryV1
    scope: AuthorizationScopeV1
    risk_level: SimulationRiskLevelV1
    decision: ToolGatewayDecisionValueV1
    confidence: float = Field(ge=0, le=100)
    timestamp: AwareDatetime
