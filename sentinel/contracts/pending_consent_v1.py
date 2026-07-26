"""Versioned record of an action waiting for a user's consent decision.

PendingConsentV1 is neither an authorization nor an execution instruction. It
cannot mint AuthorizationGrantV1 and exposes no execution method.
"""

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    Field,
    model_validator,
)

from ._base import (
    FROZEN_MODEL_CONFIG,
    NonEmptyString,
    require_timezone,
)


class PendingConsentStatusV1(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


AwareDatetime = Annotated[datetime, AfterValidator(require_timezone)]


class PendingConsentV1(BaseModel):
    """Immutable consent lifecycle record with no authority to execute."""

    model_config = FROZEN_MODEL_CONFIG

    schema_version: Literal["1.0"]
    pending_consent_id: NonEmptyString
    intent_id: NonEmptyString
    plan_id: NonEmptyString
    step_id: NonEmptyString
    tool_id: NonEmptyString
    user_id: NonEmptyString
    risk_level: NonEmptyString
    params_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    created_at: AwareDatetime
    expires_at: AwareDatetime
    status: PendingConsentStatusV1

    @model_validator(mode="after")
    def validate_lifetime(self) -> "PendingConsentV1":
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must be later than created_at")
        return self
