"""Immutable persisted safety state."""

from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import AfterValidator, Field

from sentinel.contracts import DecisionResultV1
from sentinel.contracts._base import require_timezone


class IdempotencyState(str, Enum):
    NEW = "NEW"
    PENDING = "PENDING"
    COMMITTED = "COMMITTED"
    ROLLED_BACK = "ROLLED_BACK"
    EXPIRED = "EXPIRED"


class SafetyOperationRecord(DecisionResultV1):
    correlation_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")
    migration_state: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    fallback_state: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    authority_decision: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    evidence_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    state: IdempotencyState
    created_at: Annotated[datetime, AfterValidator(require_timezone)]
    updated_at: Annotated[datetime, AfterValidator(require_timezone)]
    expires_at: Annotated[datetime, AfterValidator(require_timezone)]
