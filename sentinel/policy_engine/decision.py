"""Policy status selection from explicit rule output."""

from sentinel.contracts import PolicyEvaluationStatusV1

from .rules import RuleEvaluation


def select_policy_status(
    rules: RuleEvaluation,
) -> PolicyEvaluationStatusV1:
    if rules.violations:
        return PolicyEvaluationStatusV1.POLICY_BLOCKED
    if any(
        requirement in {"VERIFIED_EVIDENCE_REQUIRED", "TRUST_EVIDENCE_REQUIRED"} for requirement in rules.requirements
    ):
        return PolicyEvaluationStatusV1.POLICY_UNKNOWN
    if rules.requirements:
        return PolicyEvaluationStatusV1.POLICY_REVIEW_REQUIRED
    return PolicyEvaluationStatusV1.POLICY_ALLOWED
