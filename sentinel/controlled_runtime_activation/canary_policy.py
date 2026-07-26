"""Sanitized routing evidence and canary eligibility policy."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from sentinel.contracts._base import require_timezone

Scope = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.]{1,64}$")]


class CanaryRoutingEvidenceV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")
    gateway_eligibility: Literal[
        "V2_ELIGIBLE_SHADOW",
        "V2_ELIGIBLE_CANARY",
        "LEGACY_ONLY",
        "BLOCKED",
    ]
    readiness_approved: bool
    safety_healthy: bool
    rollback_available: bool
    requested_scope: Scope
    allowed_scopes: tuple[Scope, ...]
    trial_started_at: Annotated[datetime, AfterValidator(require_timezone)]
    maximum_trial_seconds: int = Field(gt=0, le=86400)
    critical_divergences: int = Field(ge=0)


class CanaryEligibilityPolicy:
    def eligible(
        self,
        evidence: CanaryRoutingEvidenceV1,
        *,
        trial_expired: bool,
    ) -> tuple[bool, tuple[str, ...]]:
        failures = []
        if evidence.gateway_eligibility != "V2_ELIGIBLE_CANARY":
            failures.append("GATEWAY_NOT_ELIGIBLE")
        if not evidence.readiness_approved:
            failures.append("READINESS_NOT_APPROVED")
        if not evidence.safety_healthy:
            failures.append("SAFETY_NOT_HEALTHY")
        if not evidence.rollback_available:
            failures.append("ROLLBACK_UNAVAILABLE")
        if evidence.requested_scope not in evidence.allowed_scopes:
            failures.append("SCOPE_NOT_ALLOWED")
        if trial_expired:
            failures.append("TRIAL_EXPIRED")
        if evidence.critical_divergences:
            failures.append("CRITICAL_DIVERGENCE")
        return not failures, tuple(failures)
