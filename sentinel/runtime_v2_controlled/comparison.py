"""Final legacy-versus-shadow comparison using sanitized metadata."""

from dataclasses import dataclass
from enum import Enum


class RuntimeComparisonStatus(str, Enum):
    MATCH = "MATCH"
    LEGACY_ONLY = "LEGACY_ONLY"
    SHADOW_ONLY = "SHADOW_ONLY"
    POLICY_DIVERGENCE = "POLICY_DIVERGENCE"
    PLAN_DIVERGENCE = "PLAN_DIVERGENCE"
    DISCOVERY_DIVERGENCE = "DISCOVERY_DIVERGENCE"
    AUTHORIZATION_DIVERGENCE = "AUTHORIZATION_DIVERGENCE"
    CRITICAL_DIVERGENCE = "CRITICAL_DIVERGENCE"


@dataclass(frozen=True)
class RuntimeComparison:
    status: RuntimeComparisonStatus
    differences: tuple[str, ...]


def compare_runtime(
    legacy: dict | None,
    shadow: dict | None,
    *,
    shadow_errors: tuple[str, ...] = (),
) -> RuntimeComparison:
    if legacy is None and shadow is None:
        return RuntimeComparison(
            RuntimeComparisonStatus.CRITICAL_DIVERGENCE,
            ("legacy_and_shadow_missing",),
        )
    if legacy is None:
        return RuntimeComparison(
            RuntimeComparisonStatus.SHADOW_ONLY,
            ("legacy_result_missing",),
        )
    if shadow is None:
        return RuntimeComparison(
            RuntimeComparisonStatus.LEGACY_ONLY,
            ("shadow_result_missing",),
        )
    differences: list[str] = []
    categories: list[RuntimeComparisonStatus] = []
    if legacy.get("intent_signature") != shadow.get("intent_signature"):
        differences.append("intent_difference")
        categories.append(RuntimeComparisonStatus.CRITICAL_DIVERGENCE)
    if (
        legacy.get("plan_signature") != shadow.get("plan_signature")
        or legacy.get("step_ids") != shadow.get("step_ids")
        or legacy.get("tool_ids") != shadow.get("tool_ids")
    ):
        differences.append("plan_difference")
        categories.append(RuntimeComparisonStatus.PLAN_DIVERGENCE)
    if legacy.get("policy_decision") != shadow.get("policy_decision"):
        differences.append("policy_decision_difference")
        categories.append(RuntimeComparisonStatus.POLICY_DIVERGENCE)
    if legacy.get("application_signature") != shadow.get("application_signature") or legacy.get(
        "launch_type"
    ) != shadow.get("launch_type"):
        differences.append("discovery_difference")
        categories.append(RuntimeComparisonStatus.DISCOVERY_DIVERGENCE)
    if legacy.get("authorization_state") != shadow.get("authorization_state"):
        differences.append("authorization_difference")
        categories.append(RuntimeComparisonStatus.AUTHORIZATION_DIVERGENCE)
    if shadow_errors:
        differences.append("shadow_error")
        categories.append(RuntimeComparisonStatus.CRITICAL_DIVERGENCE)
    unique_categories = tuple(dict.fromkeys(categories))
    if not unique_categories:
        status = RuntimeComparisonStatus.MATCH
    elif len(unique_categories) > 1 or RuntimeComparisonStatus.CRITICAL_DIVERGENCE in unique_categories:
        status = RuntimeComparisonStatus.CRITICAL_DIVERGENCE
    else:
        status = unique_categories[0]
    return RuntimeComparison(status, tuple(differences))
