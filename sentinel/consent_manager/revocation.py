"""Sanitized manual revocation record."""

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator

from sentinel.contracts import DecisionResultV1
from sentinel.contracts._base import NonEmptyString, require_timezone

AwareDatetime = Annotated[datetime, AfterValidator(require_timezone)]


class ConsentRevocationRecordV1(DecisionResultV1):
    consent_id: NonEmptyString
    correlation_id: NonEmptyString
    reason: NonEmptyString
    timestamp: AwareDatetime
    decision_source: NonEmptyString
