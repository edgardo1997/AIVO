"""Sanitized sandbox request without executable content."""

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, Field

from sentinel.contracts import (
    AuthorizationScopeV1,
    DecisionResultV1,
    SandboxCategoryV1,
)
from sentinel.contracts._base import require_timezone

AwareDatetime = Annotated[datetime, AfterValidator(require_timezone)]
HashValue = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
SafeIdentifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")]


class SandboxRequestV1(DecisionResultV1):
    request_id: SafeIdentifier
    correlation_id: SafeIdentifier
    evidence_hash: HashValue
    issuer_id: SafeIdentifier
    authorization_reference: SafeIdentifier
    requested_category: SandboxCategoryV1
    requested_scope: AuthorizationScopeV1
    timestamp: AwareDatetime
