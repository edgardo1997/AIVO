"""Pure mapping from legacy policy results to shadow rule snapshots."""

from sentinel.contracts import PolicyDecisionValueV2
from sentinel.core.policy import PolicyEffect, PolicyResult

from .engine import ShadowPolicyRule


_EFFECT_MAP = {
    PolicyEffect.ALLOW: PolicyDecisionValueV2.ALLOW,
    PolicyEffect.DENY: PolicyDecisionValueV2.DENY,
    PolicyEffect.REQUIRE_CONFIRM: (PolicyDecisionValueV2.REQUIRE_CONSENT),
}


class PolicyRuleAdapter:
    @staticmethod
    def map_effect(effect: PolicyEffect) -> PolicyDecisionValueV2:
        try:
            return _EFFECT_MAP[effect]
        except KeyError as exc:
            raise ValueError(f"unsupported legacy policy effect: {effect!r}") from exc

    @classmethod
    def adapt(
        cls,
        result: PolicyResult,
        *,
        version: str,
    ) -> tuple[ShadowPolicyRule, ...]:
        policy_ids = tuple(value.strip() for value in result.policy_id.split(",") if value.strip())
        if not policy_ids:
            raise ValueError("legacy policy_id must not be blank")
        return tuple(
            ShadowPolicyRule(
                policy_id=policy_id,
                version=version,
                decision=cls.map_effect(result.effect),
                reason=result.reason,
            )
            for policy_id in policy_ids
        )
