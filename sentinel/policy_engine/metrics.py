"""Aggregate passive policy counters."""

from dataclasses import dataclass

from sentinel.contracts import (
    DecisionResultV1,
    PolicyEvaluationStatusV1,
)


class PolicyMetricSnapshotV1(DecisionResultV1):
    evaluations: int
    allowed: int
    review_required: int
    blocked: int
    unknown: int


@dataclass
class PolicyMetrics:
    evaluations: int = 0
    allowed: int = 0
    review_required: int = 0
    blocked: int = 0
    unknown: int = 0

    def record(self, status: PolicyEvaluationStatusV1) -> None:
        self.evaluations += 1
        self.allowed += int(status is PolicyEvaluationStatusV1.POLICY_ALLOWED)
        self.review_required += int(status is PolicyEvaluationStatusV1.POLICY_REVIEW_REQUIRED)
        self.blocked += int(status is PolicyEvaluationStatusV1.POLICY_BLOCKED)
        self.unknown += int(status is PolicyEvaluationStatusV1.POLICY_UNKNOWN)

    def snapshot(self) -> PolicyMetricSnapshotV1:
        return PolicyMetricSnapshotV1(**vars(self))
