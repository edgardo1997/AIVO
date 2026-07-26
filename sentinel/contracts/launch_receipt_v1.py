"""Post-launch evidence contract for future application execution."""

from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal

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


class LaunchStateV1(str, Enum):
    LAUNCH_REQUESTED = "launch_requested"
    LAUNCHING = "launching"
    WINDOW_DETECTED = "window_detected"
    RUNNING = "running"
    FAILED = "failed"


class LaunchErrorCodeV1(str, Enum):
    APPLICATION_NOT_FOUND = "APPLICATION_NOT_FOUND"
    APPLICATION_AMBIGUOUS = "APPLICATION_AMBIGUOUS"
    LAUNCH_REJECTED = "LAUNCH_REJECTED"
    LAUNCH_TIMEOUT = "LAUNCH_TIMEOUT"
    PROCESS_EXITED = "PROCESS_EXITED"
    WINDOW_NOT_DETECTED = "WINDOW_NOT_DETECTED"
    TARGET_MISMATCH = "TARGET_MISMATCH"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    CONSENT_EXPIRED = "CONSENT_EXPIRED"


AwareDatetime = Annotated[datetime, AfterValidator(require_timezone)]


class LaunchReceiptV1(BaseModel):
    """Immutable state/evidence emitted after a future launch attempt."""

    model_config = FROZEN_MODEL_CONFIG

    schema_version: Literal["1.0"]
    receipt_id: NonEmptyString
    authorization_id: NonEmptyString
    plan_id: NonEmptyString
    step_id: NonEmptyString
    application_id: NonEmptyString
    state: LaunchStateV1
    pid: int | None = Field(default=None, gt=0)
    started_at: AwareDatetime
    completed_at: AwareDatetime | None = None
    evidence: tuple[dict[str, Any], ...] = ()
    error_code: LaunchErrorCodeV1 | None = None

    @model_validator(mode="after")
    def validate_state(self) -> "LaunchReceiptV1":
        if self.completed_at is not None and self.completed_at < self.started_at:
            raise ValueError("completed_at must not be earlier than started_at")
        if self.state == LaunchStateV1.FAILED:
            if self.error_code is None:
                raise ValueError("failed state requires error_code")
        elif self.error_code is not None:
            raise ValueError("error_code is only valid for failed state")
        if self.state == LaunchStateV1.RUNNING and not self.evidence:
            raise ValueError("running state requires evidence")
        return self
