"""In-memory aggregate isolation metrics."""

from dataclasses import dataclass

from sentinel.contracts import DecisionResultV1, IsolationStatusV1


class RuntimeIsolationMetricSnapshotV1(DecisionResultV1):
    evaluations_total: int
    ready: int
    restricted: int
    blocked: int
    invalid: int


@dataclass
class RuntimeIsolationMetrics:
    evaluations_total: int = 0
    ready: int = 0
    restricted: int = 0
    blocked: int = 0
    invalid: int = 0

    def record(self, status: IsolationStatusV1) -> None:
        self.evaluations_total += 1
        self.ready += int(status is IsolationStatusV1.ISOLATION_READY)
        self.restricted += int(status is IsolationStatusV1.ISOLATION_RESTRICTED)
        self.blocked += int(status is IsolationStatusV1.ISOLATION_BLOCKED)
        self.invalid += int(status is IsolationStatusV1.ISOLATION_INVALID)

    def snapshot(self) -> RuntimeIsolationMetricSnapshotV1:
        return RuntimeIsolationMetricSnapshotV1(**vars(self))
