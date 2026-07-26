"""Closed requests for the limited V2 executor."""

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, model_validator

from sentinel.contracts._base import FROZEN_MODEL_CONFIG, require_timezone

AwareDatetime = Annotated[datetime, AfterValidator(require_timezone)]
HashValue = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
SafeIdentifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")]


class LimitedOperationV1(str, Enum):
    SYSTEM_INFORMATION = "SYSTEM_INFORMATION"
    FILE_METADATA = "FILE_METADATA"
    APPLICATION_LAUNCH = "APPLICATION_LAUNCH"


class LimitedExecutionRequestV1(BaseModel):
    model_config = FROZEN_MODEL_CONFIG

    request_id: SafeIdentifier
    correlation_id: SafeIdentifier
    evidence_hash: HashValue
    authorization_id: SafeIdentifier
    plan_id: SafeIdentifier
    step_id: SafeIdentifier
    tool_id: SafeIdentifier
    params_hash: HashValue
    operation: LimitedOperationV1
    resource_id: SafeIdentifier | None = None
    application_id: SafeIdentifier | None = None
    timestamp: AwareDatetime
    execution_requested: Literal[True] = True

    @model_validator(mode="after")
    def validate_target(self) -> "LimitedExecutionRequestV1":
        if self.operation is LimitedOperationV1.SYSTEM_INFORMATION:
            if self.resource_id is not None or self.application_id is not None:
                raise ValueError("system information accepts no target")
        elif self.operation is LimitedOperationV1.FILE_METADATA:
            if self.resource_id is None or self.application_id is not None:
                raise ValueError("file metadata requires only resource_id")
        elif self.application_id is None or self.resource_id is not None:
            raise ValueError("application launch requires only application_id")
        return self
