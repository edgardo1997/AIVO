"""In-memory aggregate metrics for passive boundary evaluations."""

from dataclasses import dataclass

from sentinel.contracts import DecisionResultV1, ExecutionBoundaryDecisionV1


class ExecutionBoundaryMetricSnapshotV1(DecisionResultV1):
    evaluations_total: int
    blocked: int
    review_required: int
    ready: int
    invalid: int


@dataclass
class ExecutionBoundaryMetrics:
    evaluations_total: int = 0
    blocked: int = 0
    review_required: int = 0
    ready: int = 0
    invalid: int = 0

    def record(self, decision: ExecutionBoundaryDecisionV1) -> None:
        self.evaluations_total += 1
        self.blocked += int(decision is ExecutionBoundaryDecisionV1.EXECUTION_BLOCKED)
        self.review_required += int(decision is ExecutionBoundaryDecisionV1.EXECUTION_REVIEW_REQUIRED)
        self.ready += int(decision is ExecutionBoundaryDecisionV1.EXECUTION_READY)
        self.invalid += int(decision is ExecutionBoundaryDecisionV1.EXECUTION_INVALID)

    def snapshot(self) -> ExecutionBoundaryMetricSnapshotV1:
        return ExecutionBoundaryMetricSnapshotV1(**vars(self))
