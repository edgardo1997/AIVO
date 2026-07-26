"""Cross-stage comparisons for sanitized canary diagnostics."""

from dataclasses import dataclass

from sentinel.application_discovery_v2 import ApplicationShadowComparison
from sentinel.policy_v2_shadow import PolicyShadowComparison


@dataclass(frozen=True)
class RuntimeCanaryComparison:
    planner_match: bool
    discovery_match: bool
    policy_match: bool
    authorization_match: bool
    differences: tuple[str, ...]
    warnings: tuple[str, ...]

    @classmethod
    def build(
        cls,
        *,
        planner_ok: bool,
        application_comparison: ApplicationShadowComparison | None,
        policy_comparison: PolicyShadowComparison | None,
        authorization_valid: bool,
        identity_warnings: tuple[str, ...],
        schema_gaps: tuple[str, ...],
    ) -> "RuntimeCanaryComparison":
        differences: list[str] = list(schema_gaps)
        warnings = list(identity_warnings)
        discovery_match = application_comparison.match if application_comparison is not None else False
        policy_match = policy_comparison.match if policy_comparison is not None else False
        if not planner_ok:
            differences.append("planner_mismatch")
        if application_comparison is None:
            differences.append("discovery_unavailable")
        else:
            differences.extend(application_comparison.differences)
            warnings.extend(application_comparison.warnings)
        if policy_comparison is None:
            differences.append("policy_unavailable")
        else:
            differences.extend(policy_comparison.differences)
            warnings.extend(policy_comparison.warnings)
        if not authorization_valid:
            differences.append("authorization_not_validated")
        return cls(
            planner_match=planner_ok,
            discovery_match=discovery_match,
            policy_match=policy_match,
            authorization_match=authorization_valid,
            differences=tuple(dict.fromkeys(differences)),
            warnings=tuple(dict.fromkeys(warnings)),
        )

    def summary(self) -> dict:
        return {
            "status": ("MATCH" if not self.differences and not self.warnings else "DIVERGENCE"),
            "planner_match": self.planner_match,
            "discovery_match": self.discovery_match,
            "policy_match": self.policy_match,
            "authorization_match": self.authorization_match,
            "differences": self.differences,
            "warning_codes": self.warnings,
        }
