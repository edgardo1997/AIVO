"""Context-bound validation for non-authoritative canary grants."""

from datetime import datetime, timezone

from sentinel.contracts import (
    AuthorizationGrantV1,
    ExecutionPlanV2,
    ExecutionStepV2,
    IdentityContextV1,
    PolicyDecisionV2,
)

from .audit import CanaryAuditEvent, CanaryAuditLog
from .hashing import step_params_hash


class AuthorizationGrantCanaryValidator:
    def __init__(self, audit: CanaryAuditLog) -> None:
        self._audit = audit

    def validate(
        self,
        grant: AuthorizationGrantV1,
        *,
        policy_decision: PolicyDecisionV2,
        identity: IdentityContextV1,
        plan: ExecutionPlanV2,
        step: ExecutionStepV2,
        at: datetime | None = None,
        consumed_ids: set[str] | None = None,
    ) -> None:
        try:
            self._validate(
                grant,
                policy_decision=policy_decision,
                identity=identity,
                plan=plan,
                step=step,
                at=at,
                consumed_ids=consumed_ids or set(),
            )
        except (PermissionError, ValueError) as exc:
            self._audit.record(
                CanaryAuditEvent.GRANT_VALIDATION_FAILED,
                reason_code=_reason_code(exc),
            )
            raise

    @staticmethod
    def _validate(
        grant: AuthorizationGrantV1,
        *,
        policy_decision: PolicyDecisionV2,
        identity: IdentityContextV1,
        plan: ExecutionPlanV2,
        step: ExecutionStepV2,
        at: datetime | None,
        consumed_ids: set[str],
    ) -> None:
        if grant.policy_decision_id != policy_decision.decision_id:
            raise ValueError("policy_decision_mismatch")
        if policy_decision.plan_id != plan.plan_id:
            raise ValueError("policy_plan_mismatch")
        if grant.plan_id != plan.plan_id:
            raise ValueError("plan_mismatch")
        if grant.identity_context is None:
            raise ValueError("identity_context_missing")
        if grant.identity_context.identity_hash != identity.identity_hash:
            raise ValueError("identity_mismatch")
        if grant.user_id != identity.user_id:
            raise ValueError("identity_mismatch")
        authorized = next(
            (item for item in grant.authorized_steps if item.step_id == step.step_id),
            None,
        )
        if authorized is None or authorized.tool_id != step.tool_id:
            raise ValueError("step_mismatch")
        if authorized.params_hash != step_params_hash(step):
            raise ValueError("parameter_hash_mismatch")
        if grant.params_hash != plan.params_hash:
            raise ValueError("plan_hash_mismatch")
        if grant.authorization_id in consumed_ids:
            raise PermissionError("grant_replay")
        grant.assert_usable(at=at or datetime.now(timezone.utc))


def _reason_code(error: Exception) -> str:
    value = str(error)
    allowed = {
        "policy_decision_mismatch",
        "policy_plan_mismatch",
        "plan_mismatch",
        "plan_hash_mismatch",
        "identity_context_missing",
        "identity_mismatch",
        "step_mismatch",
        "parameter_hash_mismatch",
        "grant_replay",
    }
    if value in allowed:
        return value
    if "expired" in value:
        return "grant_expired"
    if "consumed" in value:
        return "grant_replay"
    return "grant_invalid"
