"""Immutable description of a hypothetical isolated context."""

from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import AfterValidator, Field

from ._base import require_timezone
from .decision import DecisionResultV1

AwareDatetime = Annotated[datetime, AfterValidator(require_timezone)]
HashValue = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
SafeIdentifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")]


class IsolationLevelV1(str, Enum):
    CONTRACT_ONLY = "CONTRACT_ONLY"
    RESTRICTED = "RESTRICTED"
    BLOCKED = "BLOCKED"


class IsolationStatusV1(str, Enum):
    ISOLATION_READY = "ISOLATION_READY"
    ISOLATION_RESTRICTED = "ISOLATION_RESTRICTED"
    ISOLATION_BLOCKED = "ISOLATION_BLOCKED"
    ISOLATION_INVALID = "ISOLATION_INVALID"


class IsolationResourceLimitsV1(DecisionResultV1):
    max_steps: int = Field(ge=0, le=32)
    max_duration_seconds: int = Field(ge=0, le=3600)
    network_access: bool = False
    system_access: bool = False
    persistent_storage: bool = False


class IsolationContextResultV1(DecisionResultV1):
    """Descriptive context only; it provisions no operating-system resource."""

    isolation_id: SafeIdentifier
    execution_reference: SafeIdentifier
    correlation_id: SafeIdentifier
    evidence_hash: HashValue
    issuer_id: SafeIdentifier
    isolation_level: IsolationLevelV1
    allowed_capabilities: tuple[SafeIdentifier, ...]
    blocked_capabilities: tuple[SafeIdentifier, ...]
    resource_limits: IsolationResourceLimitsV1
    status: IsolationStatusV1
    confidence: float = Field(ge=0, le=100)
    timestamp: AwareDatetime
