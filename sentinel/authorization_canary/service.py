"""Issue and consume grants in simulation without execution authority."""

import uuid
from datetime import datetime, timedelta, timezone

from sentinel.contracts import (
    AuthorizationGrantV1,
    AuthorizedStepV1,
    ExecutionPlanV2,
    ExecutionStepV2,
    IdentityContextV1,
    PolicyDecisionV2,
    PolicyDecisionValueV2,
)

from .audit import CanaryAuditEvent, CanaryAuditLog
from .control import authorization_canary_enabled
from .hashing import step_params_hash
from .validator import AuthorizationGrantCanaryValidator


class AuthorizationCanaryService:
    """Canary-only grant lifecycle with no runtime integration."""

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        ttl: timedelta = timedelta(minutes=5),
        audit: CanaryAuditLog | None = None,
    ) -> None:
        if ttl <= timedelta(0):
            raise ValueError("ttl must be positive")
        self._enabled = authorization_canary_enabled() if enabled is None else enabled
        self._ttl = ttl
        self.audit = audit or CanaryAuditLog()
        self.validator = AuthorizationGrantCanaryValidator(self.audit)
        self._consumed_ids: set[str] = set()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def create_grant(
        self,
        *,
        policy_decision: PolicyDecisionV2 | None,
        identity: IdentityContextV1 | None,
        plan: ExecutionPlanV2,
        step: ExecutionStepV2,
        now: datetime | None = None,
    ) -> AuthorizationGrantV1 | None:
        if not self._enabled:
            return None
        if policy_decision is None:
            raise ValueError("policy_decision is required")
        if identity is None:
            raise ValueError("identity is required")
        if policy_decision.decision is not PolicyDecisionValueV2.ALLOW:
            raise ValueError("policy decision must be ALLOW")
        if policy_decision.plan_id != plan.plan_id:
            raise ValueError("policy decision plan does not match plan")
        if not any(item.step_id == step.step_id for item in plan.steps):
            raise ValueError("step does not belong to plan")
        created_at = now or datetime.now(timezone.utc)
        authorized_step = AuthorizedStepV1(
            step_id=step.step_id,
            tool_id=step.tool_id,
            params_hash=step_params_hash(step),
        )
        grant = AuthorizationGrantV1.issue(
            authorization_id=f"canary_auth_{uuid.uuid4().hex}",
            plan_id=plan.plan_id,
            user_id=identity.user_id,
            policy_decision_id=policy_decision.decision_id,
            issuer="sentinel.authorization-canary",
            nonce=f"canary_nonce_{uuid.uuid4().hex}",
            authorized_steps=(authorized_step,),
            params_hash=plan.params_hash,
            expires_at=created_at + self._ttl,
            created_at=created_at,
            identity_context=identity,
        )
        self.audit.record(CanaryAuditEvent.GRANT_CREATED)
        return grant

    def validate(
        self,
        grant: AuthorizationGrantV1,
        *,
        policy_decision: PolicyDecisionV2,
        identity: IdentityContextV1,
        plan: ExecutionPlanV2,
        step: ExecutionStepV2,
        at: datetime | None = None,
    ) -> None:
        self.validator.validate(
            grant,
            policy_decision=policy_decision,
            identity=identity,
            plan=plan,
            step=step,
            at=at,
            consumed_ids=self._consumed_ids,
        )

    def consume_simulation(
        self,
        grant: AuthorizationGrantV1,
        *,
        at: datetime | None = None,
    ) -> AuthorizationGrantV1:
        if not self._enabled:
            raise PermissionError("authorization canary is disabled")
        consumed_at = at or datetime.now(timezone.utc)
        if grant.authorization_id in self._consumed_ids:
            self.audit.record(
                CanaryAuditEvent.GRANT_VALIDATION_FAILED,
                reason_code="grant_replay",
            )
            raise PermissionError("grant_replay")
        consumed = grant.mark_consumed(consumed_at)
        self._consumed_ids.add(grant.authorization_id)
        self.audit.record(CanaryAuditEvent.GRANT_CONSUMED_SIMULATION)
        return consumed
