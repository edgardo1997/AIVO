"""In-memory aggregate planner metrics."""

from dataclasses import dataclass

from sentinel.contracts import DecisionResultV1, ExecutionPlanStatusV1


class ExecutionPlannerMetricSnapshotV1(DecisionResultV1):
    plans_created: int
    review_required: int
    blocked: int
    invalid: int


@dataclass
class ExecutionPlannerMetrics:
    plans_created: int = 0
    review_required: int = 0
    blocked: int = 0
    invalid: int = 0

    def record(self, status: ExecutionPlanStatusV1) -> None:
        self.plans_created += int(status is ExecutionPlanStatusV1.PLAN_CREATED)
        self.review_required += int(status is ExecutionPlanStatusV1.PLAN_REVIEW_REQUIRED)
        self.blocked += int(status is ExecutionPlanStatusV1.PLAN_BLOCKED)
        self.invalid += int(status is ExecutionPlanStatusV1.PLAN_INVALID)

    def snapshot(self) -> ExecutionPlannerMetricSnapshotV1:
        return ExecutionPlannerMetricSnapshotV1(**vars(self))
