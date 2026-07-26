"""Diagnostic comparison of legacy and V2 shadow policy outcomes."""

from dataclasses import dataclass

from sentinel.contracts import PolicyDecisionV2
from sentinel.core.policy import PolicyResult
from sentinel.shadow.decision_comparison import ShadowDecisionComparison


@dataclass(frozen=True)
class PolicyShadowComparison:
    match: bool
    differences: tuple[str, ...]
    warnings: tuple[str, ...]

    @classmethod
    def compare(
        cls,
        *,
        legacy: PolicyResult,
        shadow: PolicyDecisionV2,
        legacy_policy_versions: dict[str, str] | None = None,
    ) -> "PolicyShadowComparison":
        base = ShadowDecisionComparison.compare_policy(
            legacy=legacy,
            shadow=shadow,
            expected_plan_id=shadow.plan_id,
        )
        differences = list(base.differences)
        warnings = list(base.warnings)
        legacy_ids = {item.strip() for item in legacy.policy_id.split(",") if item.strip()}
        shadow_ids = set(shadow.policy_ids)
        if legacy_ids != shadow_ids:
            differences.append("missing_policy")
        if legacy_policy_versions is not None:
            context_versions = (
                shadow.policy_context.evaluated_policy_versions if shadow.policy_context is not None else {}
            )
            for policy_id, version in legacy_policy_versions.items():
                if context_versions.get(policy_id) != version:
                    differences.append("policy_version_difference")
                    break
        return cls(
            match=not differences,
            differences=tuple(dict.fromkeys(differences)),
            warnings=tuple(dict.fromkeys(warnings)),
        )
