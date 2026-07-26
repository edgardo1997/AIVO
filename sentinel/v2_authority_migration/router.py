"""Idempotent authority selection without invoking either runtime."""

import hashlib
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field

from sentinel.contracts import DecisionResultV1

from .control import AuthorityMigrationController, AuthorityMigrationState


class AuthoritySelection(str, Enum):
    LEGACY_AUTHORITY = "LEGACY_AUTHORITY"
    V2_AUTHORITY = "V2_AUTHORITY"
    FALLBACK_LEGACY = "FALLBACK_LEGACY"


class RoutingContextV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    correlation_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")
    operation: str = Field(pattern=r"^[A-Za-z0-9_.]{1,64}$")
    readiness_approved: bool
    identity_valid: bool
    policy_context_valid: bool
    authorization_evidence_valid: bool
    critical_divergences: int = Field(ge=0)


class AuthorityDecision(DecisionResultV1):
    correlation_id: str
    selection: AuthoritySelection
    reason_code: str


class AuthorityRouter:
    def __init__(self, controller: AuthorityMigrationController) -> None:
        self.controller = controller
        self._decisions: dict[str, AuthorityDecision] = {}

    def route(self, context: RoutingContextV1) -> AuthorityDecision:
        existing = self._decisions.get(context.correlation_id)
        if existing is not None:
            return existing
        selection, reason = self._select(context)
        decision = AuthorityDecision(
            correlation_id=context.correlation_id,
            selection=selection,
            reason_code=reason,
        )
        self._decisions[context.correlation_id] = decision
        return decision

    def mark_fallback(self, correlation_id: str) -> AuthorityDecision:
        decision = AuthorityDecision(
            correlation_id=correlation_id,
            selection=AuthoritySelection.FALLBACK_LEGACY,
            reason_code="V2_FAILURE_FALLBACK",
        )
        self._decisions[correlation_id] = decision
        return decision

    def _select(
        self,
        context: RoutingContextV1,
    ) -> tuple[AuthoritySelection, str]:
        policy = self.controller.policy
        if (
            self.controller.state is not AuthorityMigrationState.LIMITED_CANARY
            or policy is None
            or self.controller.trial_expired()
        ):
            return AuthoritySelection.LEGACY_AUTHORITY, "CANARY_NOT_ACTIVE"
        conditions = (
            context.readiness_approved,
            context.identity_valid,
            context.policy_context_valid,
            context.authorization_evidence_valid,
            context.critical_divergences == 0,
            context.operation in policy.allowed_operations,
            context.operation in self.controller.scope,
        )
        if not all(conditions):
            return AuthoritySelection.LEGACY_AUTHORITY, "PRECONDITION_FAILED"
        bucket = (
            int(
                hashlib.sha256(context.correlation_id.encode("utf-8")).hexdigest()[:8],
                16,
            )
            % 10000
        )
        if bucket >= int(policy.traffic_percentage * 100):
            return AuthoritySelection.LEGACY_AUTHORITY, "OUTSIDE_CANARY_TRAFFIC"
        return AuthoritySelection.V2_AUTHORITY, "LIMITED_CANARY_APPROVED"
