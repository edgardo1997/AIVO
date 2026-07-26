"""In-memory Tool Gateway V2 counters."""

from dataclasses import dataclass

from sentinel.contracts import (
    DecisionResultV1,
    ToolGatewayDecisionValueV1,
)


class ToolGatewayMetricSnapshotV1(DecisionResultV1):
    allowed: int
    blocked: int
    review_required: int
    unknown: int
    invalid_origin: int


@dataclass
class ToolGatewayMetrics:
    allowed: int = 0
    blocked: int = 0
    review_required: int = 0
    unknown: int = 0
    invalid_origin: int = 0

    def record(
        self,
        decision: ToolGatewayDecisionValueV1,
        *,
        invalid_origin: bool,
    ) -> None:
        self.allowed += int(decision is ToolGatewayDecisionValueV1.TOOL_ALLOWED)
        self.blocked += int(decision is ToolGatewayDecisionValueV1.TOOL_BLOCKED)
        self.review_required += int(decision is ToolGatewayDecisionValueV1.TOOL_REQUIRES_REVIEW)
        self.unknown += int(decision is ToolGatewayDecisionValueV1.TOOL_UNKNOWN)
        self.invalid_origin += int(invalid_origin)

    def snapshot(self) -> ToolGatewayMetricSnapshotV1:
        return ToolGatewayMetricSnapshotV1(**vars(self))
