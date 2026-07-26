"""Human-readable representation without authority."""

from .engine import PolicyEvaluationEnvelopeV1


def render_policy_report(envelope: PolicyEvaluationEnvelopeV1) -> str:
    result = envelope.evaluation
    return "\n".join(
        (
            "SENTINEL V2 PASSIVE POLICY REPORT",
            f"Status: {result.policy_status.value}",
            f"Risk: {result.risk_level.value}",
            f"Violations: {len(result.violations)}",
            f"Requirements: {len(result.requirements)}",
            f"Confidence: {result.confidence:.2f}",
            "Authority: false",
            "Execution requested: false",
        )
    )
