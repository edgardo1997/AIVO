"""Redacted diagnostic trace emitted by passive shadow observation."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel

from ._base import FROZEN_MODEL_CONFIG, NonEmptyString, require_timezone


class ShadowExecutionTraceV1(BaseModel):
    """Immutable metadata-only trace; never contains runtime parameters."""

    model_config = FROZEN_MODEL_CONFIG

    schema_version: Literal["1.0"]
    trace_id: NonEmptyString
    timestamp: Annotated[datetime, AfterValidator(require_timezone)]
    component: NonEmptyString
    legacy_type: NonEmptyString
    versioned_type: NonEmptyString
    conversion_status: NonEmptyString
    warnings: tuple[NonEmptyString, ...] = ()
    differences: tuple[NonEmptyString, ...] = ()
    correlation_ids: dict[NonEmptyString, NonEmptyString]
