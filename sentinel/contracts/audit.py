"""Sanitized audit event contract for V2 control-plane evidence."""

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator

from ._base import NonEmptyString, require_timezone
from .authority import NonAuthoritativeDecisionV1

AwareDatetime = Annotated[datetime, AfterValidator(require_timezone)]


class AuditEventV1(NonAuthoritativeDecisionV1):
    """Immutable audit fact containing identifiers and sanitized results."""

    event_id: NonEmptyString
    event_type: NonEmptyString
    timestamp: AwareDatetime
    correlation_id: NonEmptyString
    evidence_hash: NonEmptyString
    issuer_id: NonEmptyString
    result: NonEmptyString
