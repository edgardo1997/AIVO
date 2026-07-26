"""Pure adapter from legacy PolicyResult to final PolicyDecisionV2 shape."""

from copy import deepcopy
from datetime import datetime, timezone

from sentinel.contracts import (
    PolicyContextV1,
    PolicyDecisionV2,
    PolicyDecisionValueV2,
)
from sentinel.core.policy import PolicyEffect, PolicyResult

from ._ids import generated_id, require_id


_DECISION_MAP = {
    PolicyEffect.ALLOW: PolicyDecisionValueV2.ALLOW,
    PolicyEffect.REQUIRE_CONFIRM: PolicyDecisionValueV2.REQUIRE_CONSENT,
    PolicyEffect.DENY: PolicyDecisionValueV2.DENY,
}


def policy_result_to_v2(
    result: PolicyResult,
    *,
    plan_id: str,
    decision_id: str | None = None,
    timestamp: datetime | None = None,
    policy_context: PolicyContextV1 | None = None,
) -> PolicyDecisionV2:
    """Convert a legacy policy result while preserving its complete context."""
    if not isinstance(result, PolicyResult):
        raise TypeError("result must be a sentinel.core.policy.PolicyResult")

    try:
        decision = _DECISION_MAP[result.effect]
    except KeyError as exc:
        raise ValueError(f"unsupported legacy policy effect: {result.effect!r}") from exc

    policy_ids = tuple(policy_id.strip() for policy_id in result.policy_id.split(",") if policy_id.strip())
    if not policy_ids:
        raise ValueError("legacy PolicyResult.policy_id must not be blank")

    return PolicyDecisionV2(
        schema_version="2.0",
        decision_id=decision_id or generated_id("decision"),
        plan_id=require_id(plan_id, "plan_id"),
        decision=decision,
        policy_ids=policy_ids,
        reason=result.reason,
        risk_context=deepcopy(result.context),
        timestamp=timestamp or datetime.now(timezone.utc),
        policy_context=policy_context,
    )
