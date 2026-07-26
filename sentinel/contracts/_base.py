"""Shared validation primitives for versioned Sentinel contracts."""

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, ConfigDict, StringConstraints


def _not_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


NonEmptyString = Annotated[
    str,
    StringConstraints(min_length=1),
    AfterValidator(_not_blank),
]

FROZEN_MODEL_CONFIG = ConfigDict(
    extra="forbid",
    frozen=True,
    use_enum_values=False,
)


def require_timezone(value: datetime) -> datetime:
    """Reject ambiguous timestamps that do not carry an explicit timezone."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include timezone information")
    return value
