"""Pure legacy-versus-shadow decision comparison."""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sentinel.contracts import PolicyDecisionValueV2
from sentinel.contracts import PolicyDecisionV2
from sentinel.core.policy import PolicyEffect, PolicyResult


class ShadowDecisionComparisonStatus(str, Enum):
    MATCH = "MATCH"
    DIVERGENCE = "DIVERGENCE"
    ERROR = "ERROR"


@dataclass(frozen=True)
class ShadowDecisionComparison:
    comparison_id: str
    component: str
    timestamp: datetime
    legacy_decision: str
    shadow_decision: str
    same_decision: bool
    status: ShadowDecisionComparisonStatus
    differences: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @classmethod
    def compare(
        cls,
        *,
        component: str,
        legacy_decision: Any,
        shadow_decision: Any,
        missing_information: tuple[str, ...] = (),
    ) -> "ShadowDecisionComparison":
        warnings = tuple(f"missing_information: {field}" for field in missing_information)
        try:
            legacy = _normalize(legacy_decision)
            shadow = _normalize(shadow_decision)
        except ValueError as exc:
            return cls(
                comparison_id=f"comparison_{uuid.uuid4().hex}",
                component=component,
                timestamp=datetime.now(timezone.utc),
                legacy_decision=str(legacy_decision),
                shadow_decision=str(shadow_decision),
                same_decision=False,
                status=ShadowDecisionComparisonStatus.ERROR,
                differences=(str(exc),),
                warnings=warnings,
            )
        same = legacy == shadow
        differences = list(missing_information)
        if not same:
            differences.append(f"decision_changed:{legacy}->{shadow}")
        return cls(
            comparison_id=f"comparison_{uuid.uuid4().hex}",
            component=component,
            timestamp=datetime.now(timezone.utc),
            legacy_decision=legacy,
            shadow_decision=shadow,
            same_decision=same,
            status=(ShadowDecisionComparisonStatus.MATCH if same else ShadowDecisionComparisonStatus.DIVERGENCE),
            differences=tuple(differences),
            warnings=warnings,
        )

    @classmethod
    def compare_policy(
        cls,
        *,
        legacy: PolicyResult,
        shadow: PolicyDecisionV2,
        expected_plan_id: str | None = None,
    ) -> "ShadowDecisionComparison":
        """Compare policy structures without evaluating either policy."""
        base = cls.compare(
            component="policy",
            legacy_decision=legacy.effect,
            shadow_decision=shadow.decision,
        )
        differences = list(base.differences)
        warnings = list(base.warnings)
        if expected_plan_id and shadow.plan_id != expected_plan_id:
            differences.append("plan_different")
        if shadow.policy_context is None:
            differences.extend(
                (
                    "missing_context",
                    "missing_identity",
                    "missing_policy_version",
                )
            )
            warnings.append("missing_context: PolicyContextV1")
        else:
            missing_versions = set(shadow.policy_ids) - set(shadow.policy_context.evaluated_policy_versions)
            if missing_versions:
                differences.append("missing_policy_version")
        if not legacy.context:
            warnings.append("missing_context: legacy PolicyResult.context")
        same = not differences
        return cls(
            comparison_id=base.comparison_id,
            component=base.component,
            timestamp=base.timestamp,
            legacy_decision=base.legacy_decision,
            shadow_decision=base.shadow_decision,
            same_decision=same,
            status=(ShadowDecisionComparisonStatus.MATCH if same else ShadowDecisionComparisonStatus.DIVERGENCE),
            differences=tuple(dict.fromkeys(differences)),
            warnings=tuple(dict.fromkeys(warnings)),
        )


def _normalize(value: Any) -> str:
    if isinstance(value, PolicyEffect):
        return {
            PolicyEffect.ALLOW: "ALLOW",
            PolicyEffect.DENY: "DENY",
            PolicyEffect.REQUIRE_CONFIRM: "REQUIRE_CONSENT",
        }[value]
    if isinstance(value, PolicyDecisionValueV2):
        return value.value
    raw = str(value).strip().upper()
    aliases = {
        "APPROVE": "ALLOW",
        "REQUIRE_CONFIRM": "REQUIRE_CONSENT",
    }
    raw = aliases.get(raw, raw)
    if raw not in {"ALLOW", "DENY", "REQUIRE_CONSENT"}:
        raise ValueError(f"unsupported decision value: {value!r}")
    return raw
