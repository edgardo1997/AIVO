"""Immutable receipt for the narrowly-scoped V2 execution boundary."""

from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, Field, model_validator

from ._base import FROZEN_MODEL_CONFIG, require_timezone
from .launch_receipt_v1 import LaunchReceiptV1

AwareDatetime = Annotated[datetime, AfterValidator(require_timezone)]
HashValue = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
SafeIdentifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")]


class LimitedExecutionStatusV1(str, Enum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    FALLBACK_REQUIRED = "FALLBACK_REQUIRED"
    BLOCKED = "BLOCKED"


class LimitedExecutionReceiptV1(BaseModel):
    model_config = FROZEN_MODEL_CONFIG

    schema_version: Literal["1.0"] = "1.0"
    receipt_id: SafeIdentifier
    correlation_id: SafeIdentifier
    evidence_hash: HashValue
    authorization_id: SafeIdentifier
    plan_id: SafeIdentifier
    step_id: SafeIdentifier
    tool_id: SafeIdentifier
    params_hash: HashValue
    status: LimitedExecutionStatusV1
    started_at: AwareDatetime
    completed_at: AwareDatetime
    result_code: SafeIdentifier
    sanitized_result: dict[str, Any] = Field(default_factory=dict)
    rollback_state: Literal["NOT_REQUIRED", "LOGICAL_ONLY", "FALLBACK_AVAILABLE"]
    fallback_available: bool
    application_receipt: LaunchReceiptV1 | None = None
    authority: Literal[False] = False

    @model_validator(mode="after")
    def validate_receipt(self) -> "LimitedExecutionReceiptV1":
        if self.completed_at < self.started_at:
            raise ValueError("completed_at must not precede started_at")
        forbidden = {
            "command",
            "arguments",
            "path",
            "prompt",
            "secret",
            "token",
        }
        if forbidden.intersection(key.lower() for key in self.sanitized_result):
            raise ValueError("sensitive execution result field")
        return self
