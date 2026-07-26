"""Reference-only request for hypothetical plan traversal."""

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, Field

from sentinel.contracts import AuthorizationScopeV1, DecisionResultV1
from sentinel.contracts._base import require_timezone

AwareDatetime = Annotated[datetime, AfterValidator(require_timezone)]
HashValue = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
SafeIdentifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")]


class SandboxExecutionRequestV1(DecisionResultV1):
    request_id: SafeIdentifier
    plan_id: SafeIdentifier
    correlation_id: SafeIdentifier
    evidence_hash: HashValue
    issuer_id: SafeIdentifier
    authorization_reference: SafeIdentifier
    policy_reference: SafeIdentifier
    scope: AuthorizationScopeV1
    timestamp: AwareDatetime
    valid_until: AwareDatetime
