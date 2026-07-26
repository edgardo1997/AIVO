"""Visible deterministic rules over existing V2 contract states."""

from dataclasses import dataclass

from sentinel.contracts import (
    EvidenceIntegrityStatusV1,
    HealthStateV1,
    PolicyViolationSeverityV1,
    PolicyViolationV1,
    ReadinessStateValueV1,
    SimulationActionTypeV1,
    SimulationResultV1,
    SimulationRiskLevelV1,
)
from sentinel.recommendation_engine import (
    RecommendationResultV1,
    RecommendationValue,
)
from sentinel.v2_trust_evaluation import ConfidenceState, TrustEvaluationResultV1


@dataclass(frozen=True)
class RuleEvaluation:
    violations: tuple[PolicyViolationV1, ...]
    requirements: tuple[str, ...]


def evaluate_rules(
    *,
    simulation: SimulationResultV1,
    recommendation: RecommendationResultV1,
    trust: TrustEvaluationResultV1,
    readiness: ReadinessStateValueV1,
    health: HealthStateV1,
    integrity: EvidenceIntegrityStatusV1,
) -> RuleEvaluation:
    violations: list[PolicyViolationV1] = []
    requirements: list[str] = []

    if integrity is EvidenceIntegrityStatusV1.INVALID:
        violations.append(
            _violation(
                "EVIDENCE_INVALID",
                PolicyViolationSeverityV1.CRITICAL,
                "Evidence integrity is invalid.",
                "Policy evaluation cannot trust altered evidence.",
            )
        )
    if simulation.risk_level is SimulationRiskLevelV1.CRITICAL:
        violations.append(
            _violation(
                "CRITICAL_RISK_BLOCK",
                PolicyViolationSeverityV1.CRITICAL,
                "The inherited simulation risk is critical.",
                "Critical hypothetical impact is never policy-compatible.",
            )
        )
    elif simulation.risk_level is SimulationRiskLevelV1.HIGH:
        violations.append(
            _violation(
                "HIGH_RISK_BLOCK",
                PolicyViolationSeverityV1.HIGH,
                "The inherited simulation risk is high.",
                "High hypothetical impact requires policy blocking.",
            )
        )
    if health in {HealthStateV1.CRITICAL, HealthStateV1.DEGRADED}:
        violations.append(
            _violation(
                "UNHEALTHY_CONTROL_PLANE",
                PolicyViolationSeverityV1.HIGH,
                "The supplied health contract is not acceptable.",
                "Policy review requires a healthy or observing control plane.",
            )
        )
    if readiness in {
        ReadinessStateValueV1.BLOCKED,
        ReadinessStateValueV1.NOT_APPROVED,
    }:
        violations.append(
            _violation(
                "READINESS_BLOCK",
                PolicyViolationSeverityV1.HIGH,
                "The supplied readiness contract blocks review.",
                "Policy cannot proceed against a blocking readiness state.",
            )
        )
    if recommendation.evaluation.recommendation is RecommendationValue.BLOCK_RECOMMENDATION:
        violations.append(
            _violation(
                "RECOMMENDATION_BLOCK",
                PolicyViolationSeverityV1.HIGH,
                "The recommendation contract blocks review.",
                "Policy preserves the existing passive recommendation.",
            )
        )

    if integrity in {
        EvidenceIntegrityStatusV1.UNKNOWN,
        EvidenceIntegrityStatusV1.SIGNED,
    }:
        requirements.append("VERIFIED_EVIDENCE_REQUIRED")
    if trust.confidence is ConfidenceState.UNKNOWN:
        requirements.append("TRUST_EVIDENCE_REQUIRED")
    if not violations and not requirements:
        if simulation.action_type in {
            SimulationActionTypeV1.DELETE_FILE,
            SimulationActionTypeV1.INSTALL_APPLICATION,
            SimulationActionTypeV1.MODIFY_CONFIGURATION,
        }:
            requirements.append("HUMAN_REVIEW_REQUIRED")
        elif simulation.risk_level is not SimulationRiskLevelV1.LOW or not simulation.rollback_available:
            requirements.append("HUMAN_REVIEW_REQUIRED")

    return RuleEvaluation(
        violations=tuple(violations),
        requirements=tuple(sorted(set(requirements))),
    )


def _violation(
    rule_id: str,
    severity: PolicyViolationSeverityV1,
    description: str,
    reason: str,
) -> PolicyViolationV1:
    return PolicyViolationV1(
        rule_id=rule_id,
        severity=severity,
        description=description,
        reason=reason,
    )
