"""Sanitized manual authorization revocation record."""

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator

from sentinel.contracts import DecisionResultV1
from sentinel.contracts._base import NonEmptyString, require_timezone

AwareDatetime = Annotated[datetime, AfterValidator(require_timezone)]


class AuthorizationRevocationRecordV1(DecisionResultV1):
    grant_id: NonEmptyString
    correlation_id: NonEmptyString
    reason: NonEmptyString
    actor: NonEmptyString
    timestamp: AwareDatetime
