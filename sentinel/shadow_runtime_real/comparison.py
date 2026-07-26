"""Deterministic comparison of sanitized Legacy and V2 outcomes."""

import hashlib
import json

from sentinel.contracts import (
    ExecutionPlanResultV1,
    PolicyEvaluationStatusV1,
)
from sentinel.v2_unified_pipeline import UnifiedPipelineResultV1

from .models import (
    DivergenceClassificationV1,
    DivergenceSeverityV1,
    LegacyRuntimeSnapshotV1,
    ShadowComparisonResultV1,
    ShadowDivergenceV1,
)


def shadow_plan_fingerprint(plan: ExecutionPlanResultV1) -> str:
    payload = {
        "action_category": plan.action_category.value,
        "steps": [
            {
                "step_id": step.step_id,
                "sequence": step.sequence,
                "description": step.description,
                "verification": step.verification,
            }
            for step in plan.steps
        ],
        "rollback_strategy": plan.rollback_strategy,
        "risk_level": plan.risk_level.value,
        "status": plan.status.value,
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compare_legacy_to_v2(
    legacy: LegacyRuntimeSnapshotV1,
    shadow: UnifiedPipelineResultV1,
) -> ShadowComparisonResultV1:
    divergences: list[ShadowDivergenceV1] = []
    if legacy.correlation_id != shadow.correlation_id:
        divergences.append(
            _divergence(
                "CORRELATION",
                legacy.correlation_id,
                shadow.correlation_id,
                DivergenceClassificationV1.CRITICAL_DIVERGENCE,
                DivergenceSeverityV1.CRITICAL,
                "ORIGIN_MISMATCH",
            )
        )

    shadow_plan = shadow_plan_fingerprint(shadow.plan) if shadow.plan is not None else "MISSING"
    if legacy.plan_fingerprint != shadow_plan:
        divergences.append(
            _divergence(
                "PLAN",
                "LEGACY_HASH",
                "V2_HASH" if shadow.plan is not None else "MISSING",
                DivergenceClassificationV1.EXPECTED_DIFFERENCE,
                DivergenceSeverityV1.MEDIUM,
                "PLAN_FINGERPRINT_DIFFERS",
            )
        )

    shadow_policy = _policy_value(shadow)
    if legacy.policy_decision != shadow_policy:
        classification, severity, reason = _policy_classification(
            legacy.policy_decision,
            shadow_policy,
        )
        divergences.append(
            _divergence(
                "POLICY",
                legacy.policy_decision,
                shadow_policy,
                classification,
                severity,
                reason,
            )
        )

    shadow_scope = (
        shadow.authorization.scope.value
        if shadow.authorization is not None and shadow.authorization.scope is not None
        else "MISSING"
    )
    if legacy.scope.value != shadow_scope:
        escalation = _scope_rank(shadow_scope) > _scope_rank(legacy.scope.value)
        divergences.append(
            _divergence(
                "SCOPE",
                legacy.scope.value,
                shadow_scope,
                (
                    DivergenceClassificationV1.CRITICAL_DIVERGENCE
                    if escalation
                    else DivergenceClassificationV1.INFORMATION_LOSS
                ),
                (DivergenceSeverityV1.CRITICAL if escalation else DivergenceSeverityV1.HIGH),
                "SCOPE_ESCALATION" if escalation else "SCOPE_NOT_REPRESENTED",
            )
        )

    if legacy.result_code != shadow.status.value:
        critical = legacy.result_code in {"BLOCKED", "FAILED", "DENIED"} and shadow.status.value == "COMPLETED"
        divergences.append(
            _divergence(
                "RESULT",
                legacy.result_code,
                shadow.status.value,
                (
                    DivergenceClassificationV1.CRITICAL_DIVERGENCE
                    if critical
                    else DivergenceClassificationV1.EXPECTED_DIFFERENCE
                ),
                (DivergenceSeverityV1.CRITICAL if critical else DivergenceSeverityV1.MEDIUM),
                "LEGACY_BLOCK_BYPASS" if critical else "RESULT_DIFFERS",
            )
        )

    for field in legacy.lost_fields:
        divergences.append(
            _divergence(
                field,
                "PRESENT",
                "MISSING",
                DivergenceClassificationV1.INFORMATION_LOSS,
                DivergenceSeverityV1.HIGH,
                "LEGACY_FIELD_LOST",
            )
        )

    digest = hashlib.sha256(
        (
            f"{legacy.snapshot_id}:{shadow.correlation_id}:"
            + ",".join(f"{item.field}:{item.reason}" for item in divergences)
        ).encode("utf-8")
    ).hexdigest()[:32]
    return ShadowComparisonResultV1(
        comparison_id=f"shadow-comparison:{digest}",
        correlation_id=shadow.correlation_id,
        evidence_hash=shadow.evidence_hash,
        timestamp=shadow.timestamp,
        divergences=tuple(divergences),
        critical_count=sum(item.severity is DivergenceSeverityV1.CRITICAL for item in divergences),
        information_loss_count=sum(
            item.classification is DivergenceClassificationV1.INFORMATION_LOSS for item in divergences
        ),
        matched=not divergences,
    )


def _policy_value(shadow: UnifiedPipelineResultV1) -> str:
    if shadow.policy is None:
        return "MISSING"
    return {
        PolicyEvaluationStatusV1.POLICY_ALLOWED: "ALLOW",
        PolicyEvaluationStatusV1.POLICY_REVIEW_REQUIRED: "REQUIRE_CONSENT",
        PolicyEvaluationStatusV1.POLICY_BLOCKED: "DENY",
        PolicyEvaluationStatusV1.POLICY_UNKNOWN: "UNKNOWN",
    }[shadow.policy.policy_status]


def _policy_classification(legacy: str, shadow: str):
    if legacy == "DENY" and shadow in {"ALLOW", "REQUIRE_CONSENT"}:
        return (
            DivergenceClassificationV1.CRITICAL_DIVERGENCE,
            DivergenceSeverityV1.CRITICAL,
            "LEGACY_POLICY_BYPASS",
        )
    if legacy == "ALLOW" and shadow in {"DENY", "REQUIRE_CONSENT"}:
        return (
            DivergenceClassificationV1.SECURITY_IMPROVEMENT,
            DivergenceSeverityV1.LOW,
            "V2_MORE_RESTRICTIVE",
        )
    return (
        DivergenceClassificationV1.V2_REGRESSION,
        DivergenceSeverityV1.HIGH,
        "POLICY_SEMANTICS_DIFFER",
    )


def _scope_rank(value: str) -> int:
    return {
        "MISSING": -1,
        "READ_ONLY": 0,
        "SIMULATION_ONLY": 1,
        "USER_APPROVED_ACTION": 2,
    }.get(value, 3)


def _divergence(
    field: str,
    legacy: str,
    v2: str,
    classification: DivergenceClassificationV1,
    severity: DivergenceSeverityV1,
    reason: str,
) -> ShadowDivergenceV1:
    return ShadowDivergenceV1(
        field=field,
        classification=classification,
        severity=severity,
        legacy_value=_safe_code(legacy),
        v2_value=_safe_code(v2),
        reason=reason,
    )


def _safe_code(value: str) -> str:
    normalized = "".join(character if character.isalnum() else "_" for character in str(value).upper()).strip("_")
    return (normalized or "UNKNOWN")[:64]
