"""Signed, immutable descriptions of passive V2 tools."""

from datetime import datetime
from enum import Enum
from typing import Annotated, Any

from pydantic import AfterValidator, Field, field_validator, model_validator

from ._base import require_timezone
from .authorization_grant_v1 import AuthorizationScopeV1
from .authority import NonAuthoritativeDecisionV1
from .simulation_result_v1 import SimulationRiskLevelV1
from .tool_gateway_decision_result_v1 import ToolCategoryV1

AwareDatetime = Annotated[datetime, AfterValidator(require_timezone)]
HashValue = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
SafeIdentifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")]


class ToolParameterTypeV1(str, Enum):
    BOOLEAN = "BOOLEAN"
    INTEGER = "INTEGER"
    ENUM = "ENUM"
    IDENTIFIER = "IDENTIFIER"


class ToolParameterSpecV1(NonAuthoritativeDecisionV1):
    name: SafeIdentifier
    parameter_type: ToolParameterTypeV1
    required: bool = False
    enum_values: tuple[SafeIdentifier, ...] = ()
    minimum: int | None = None
    maximum: int | None = None

    @model_validator(mode="after")
    def validate_constraints(self) -> "ToolParameterSpecV1":
        if self.parameter_type is ToolParameterTypeV1.ENUM:
            if not self.enum_values:
                raise ValueError("ENUM requires enum_values")
        elif self.enum_values:
            raise ValueError("enum_values are only valid for ENUM")
        if self.minimum is not None and self.maximum is not None:
            if self.minimum > self.maximum:
                raise ValueError("minimum must not exceed maximum")
        return self


class ToolSpecificationV1(NonAuthoritativeDecisionV1):
    tool_id: SafeIdentifier
    version: SafeIdentifier
    category: ToolCategoryV1
    allowed_scopes: tuple[AuthorizationScopeV1, ...]
    risk_level: SimulationRiskLevelV1
    parameters: tuple[ToolParameterSpecV1, ...] = ()
    specification_hash: HashValue

    @field_validator("allowed_scopes")
    @classmethod
    def require_scopes(
        cls,
        value: tuple[AuthorizationScopeV1, ...],
    ) -> tuple[AuthorizationScopeV1, ...]:
        if not value or len(set(value)) != len(value):
            raise ValueError("allowed_scopes must be non-empty and unique")
        return value

    @field_validator("parameters")
    @classmethod
    def require_unique_parameters(
        cls,
        value: tuple[ToolParameterSpecV1, ...],
    ) -> tuple[ToolParameterSpecV1, ...]:
        names = tuple(item.name for item in value)
        if len(names) != len(set(names)):
            raise ValueError("parameter names must be unique")
        return value


class SignedToolCatalogV1(NonAuthoritativeDecisionV1):
    catalog_id: SafeIdentifier
    version: SafeIdentifier
    issuer_id: SafeIdentifier
    created_at: AwareDatetime
    entries: tuple[ToolSpecificationV1, ...]
    catalog_hash: HashValue
    signature: str = Field(min_length=32, max_length=256)

    @field_validator("entries")
    @classmethod
    def require_unique_tools(
        cls,
        value: tuple[ToolSpecificationV1, ...],
    ) -> tuple[ToolSpecificationV1, ...]:
        identities = tuple((item.tool_id, item.version) for item in value)
        if not value or len(identities) != len(set(identities)):
            raise ValueError("catalog tools must be non-empty and unique")
        return value


ToolParametersV1 = dict[str, bool | int | str]


def reject_unsafe_parameter_value(value: Any) -> None:
    if isinstance(value, (dict, list, tuple, bytes)):
        raise ValueError("nested or binary parameters are forbidden")
