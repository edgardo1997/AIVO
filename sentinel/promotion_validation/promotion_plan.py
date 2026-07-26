"""Immutable hypothetical promotion plan with mandatory rollback."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from sentinel.contracts._base import NonEmptyString


class PromotionPlanV1(BaseModel):
    """Describes a candidate promotion; it cannot activate anything."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"]
    candidate_component: NonEmptyString
    current_version: NonEmptyString
    target_version: NonEmptyString
    required_dependencies: tuple[NonEmptyString, ...]
    known_risks: tuple[NonEmptyString, ...]
    approval_requirements: tuple[NonEmptyString, ...] = Field(min_length=1)
    rollback_plan: tuple[NonEmptyString, ...] = Field(min_length=1)

    @field_validator("target_version")
    @classmethod
    def versions_must_differ(cls, value: str, info) -> str:
        if value == info.data.get("current_version"):
            raise ValueError("target_version must differ from current_version")
        return value
