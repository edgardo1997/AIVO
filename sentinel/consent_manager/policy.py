"""Compatibility checks over the passive policy result."""

from sentinel.contracts import (
    PolicyEvaluationResultV1,
    PolicyEvaluationStatusV1,
)


def policy_accepts_consent_request(
    policy: PolicyEvaluationResultV1,
) -> bool:
    return policy.policy_status in {
        PolicyEvaluationStatusV1.POLICY_ALLOWED,
        PolicyEvaluationStatusV1.POLICY_REVIEW_REQUIRED,
    }
