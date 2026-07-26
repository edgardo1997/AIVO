"""Sanitized Tool Gateway request with no executable payload."""

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, Field, field_validator

from sentinel.contracts import (
    AuthorizationScopeV1,
    DecisionResultV1,
    ToolCategoryV1,
)
from sentinel.contracts._base import require_timezone

AwareDatetime = Annotated[datetime, AfterValidator(require_timezone)]
HashValue = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
SafeIdentifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")]


class ToolParameterValueV1(DecisionResultV1):
    name: SafeIdentifier
    value: bool | int | SafeIdentifier


class ToolRequestV1(DecisionResultV1):
    request_id: SafeIdentifier
    correlation_id: SafeIdentifier
    evidence_hash: HashValue
    issuer_id: SafeIdentifier
    authorization_reference: SafeIdentifier
    plan_id: SafeIdentifier
    step_id: SafeIdentifier
    tool_id: SafeIdentifier
    tool_version: SafeIdentifier
    requested_tool_category: ToolCategoryV1
    requested_scope: AuthorizationScopeV1
    parameters: tuple[ToolParameterValueV1, ...] = ()
    params_hash: HashValue
    timestamp: AwareDatetime

    @field_validator("parameters")
    @classmethod
    def unique_parameter_names(
        cls,
        value: tuple[ToolParameterValueV1, ...],
    ) -> tuple[ToolParameterValueV1, ...]:
        names = tuple(item.name for item in value)
        if len(names) != len(set(names)):
            raise ValueError("parameter names must be unique")
        return value

    def parameter_values(self) -> dict[str, bool | int | str]:
        return {item.name: item.value for item in self.parameters}
