"""Policy compatibility for passive authorization evaluation."""

from sentinel.contracts import (
    PolicyEvaluationResultV1,
    PolicyEvaluationStatusV1,
)


def policy_allows_evaluation(policy: PolicyEvaluationResultV1) -> bool:
    return policy.policy_status in {
        PolicyEvaluationStatusV1.POLICY_ALLOWED,
        PolicyEvaluationStatusV1.POLICY_REVIEW_REQUIRED,
    }
