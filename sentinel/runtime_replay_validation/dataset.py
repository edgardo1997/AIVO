"""Strict hash-only replay dataset record."""

from datetime import datetime
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from sentinel.contracts._base import (
    NonEmptyString,
    require_timezone,
)


class ReplayDatasetV1(BaseModel):
    """One historical or synthetic event with no original payload."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(pattern=r"^[A-Za-z0-9._:-]{1,128}$")
    event_type: str = Field(pattern=r"^[A-Za-z0-9._:-]{1,128}$")
    version: NonEmptyString
    sanitized_payload_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    timestamp: Annotated[datetime, AfterValidator(require_timezone)]

    @field_validator("version")
    @classmethod
    def safe_version(cls, value: str) -> str:
        if len(value) > 32 or any(character.isspace() for character in value) or "/" in value or "\\" in value:
            raise ValueError("version must be a sanitized identifier")
        return value
