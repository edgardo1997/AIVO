"""Non-authoritative policy evaluation over versioned contracts."""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sentinel.contracts import (
    ApplicationDescriptorV1,
    ExecutionPlanV2,
    IdentityContextV1,
    IntentV2,
    PolicyContextV1,
    PolicyDecisionV2,
    PolicyDecisionValueV2,
)

from .control import policy_shadow_enabled


@dataclass(frozen=True)
class ShadowPolicyRule:
    policy_id: str
    version: str
    decision: PolicyDecisionValueV2
    reason: str


@dataclass(frozen=True)
class ShadowPolicyEvaluation:
    decision: PolicyDecisionV2 | None
    warnings: tuple[str, ...]
    evaluated_policies: tuple[str, ...]


class PolicyEngineV2Shadow:
    """Evaluate snapshots only; never authorizes or affects runtime."""

    def __init__(self, *, enabled: bool | None = None) -> None:
        self._enabled = policy_shadow_enabled() if enabled is None else enabled

    @property
    def enabled(self) -> bool:
        return self._enabled

    def evaluate(
        self,
        *,
        intent: IntentV2,
        plan: ExecutionPlanV2,
        identity: IdentityContextV1 | None,
        policy_context: PolicyContextV1 | None,
        application: ApplicationDescriptorV1,
        rules: tuple[ShadowPolicyRule, ...],
    ) -> ShadowPolicyEvaluation:
        if not self._enabled:
            return ShadowPolicyEvaluation(
                decision=None,
                warnings=("shadow_disabled",),
                evaluated_policies=(),
            )
        warnings = self._validate_context(
            intent=intent,
            plan=plan,
            identity=identity,
            policy_context=policy_context,
            application=application,
            rules=rules,
        )
        if not rules:
            raise ValueError("at least one shadow policy rule is required")
        decision_value = _aggregate(rule.decision for rule in rules)
        usable_context = (
            policy_context
            if not any(
                warning.startswith(
                    (
                        "missing_context",
                        "missing_identity",
                        "missing_policy_version",
                        "context_mismatch",
                    )
                )
                for warning in warnings
            )
            else None
        )
        now = datetime.now(timezone.utc)
        decision = PolicyDecisionV2(
            schema_version="2.0",
            decision_id=f"shadow_policy_{uuid.uuid4().hex}",
            plan_id=plan.plan_id,
            decision=decision_value,
            policy_ids=tuple(rule.policy_id for rule in rules),
            reason=_reason(decision_value),
            risk_context={
                "risk_level": (policy_context.risk_level if policy_context is not None else "unknown"),
                "application_provider": application.provider,
            },
            timestamp=now,
            policy_context=usable_context,
        )
        return ShadowPolicyEvaluation(
            decision=decision,
            warnings=tuple(warnings),
            evaluated_policies=tuple(rule.policy_id for rule in rules),
        )

    @staticmethod
    def _validate_context(
        *,
        intent: IntentV2,
        plan: ExecutionPlanV2,
        identity: IdentityContextV1 | None,
        policy_context: PolicyContextV1 | None,
        application: ApplicationDescriptorV1,
        rules: tuple[ShadowPolicyRule, ...],
    ) -> list[str]:
        warnings: list[str] = []
        if plan.intent_id != intent.intent_id:
            warnings.append("context_mismatch: intent_id")
        if identity is None:
            warnings.append("missing_identity")
        if policy_context is None:
            warnings.append("missing_context")
        else:
            if policy_context.plan_id != plan.plan_id:
                warnings.append("context_mismatch: plan_id")
            if policy_context.intent_id != intent.intent_id:
                warnings.append("context_mismatch: policy intent_id")
            if identity is not None and policy_context.user_id != identity.user_id:
                warnings.append("missing_identity: identity mismatch")
            versions = policy_context.evaluated_policy_versions
            for rule in rules:
                if versions.get(rule.policy_id) != rule.version:
                    warnings.append(f"missing_policy_version: {rule.policy_id}")
        if not application.resolver_evidence:
            warnings.append("missing_context: resolver evidence")
        return warnings


def _aggregate(
    decisions,
) -> PolicyDecisionValueV2:
    values = tuple(decisions)
    if PolicyDecisionValueV2.DENY in values:
        return PolicyDecisionValueV2.DENY
    if PolicyDecisionValueV2.REQUIRE_CONSENT in values:
        return PolicyDecisionValueV2.REQUIRE_CONSENT
    return PolicyDecisionValueV2.ALLOW


def _reason(decision: PolicyDecisionValueV2) -> str:
    return {
        PolicyDecisionValueV2.ALLOW: "Shadow policies recommend allow",
        PolicyDecisionValueV2.DENY: "Shadow policies recommend deny",
        PolicyDecisionValueV2.REQUIRE_CONSENT: ("Shadow policies recommend user consent"),
    }[decision]
