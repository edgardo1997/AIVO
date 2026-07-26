"""In-memory aggregate sandbox execution metrics."""

from dataclasses import dataclass

from sentinel.contracts import DecisionResultV1, SandboxExecutionStatusV1


class ExecutorSandboxMetricSnapshotV1(DecisionResultV1):
    simulations_total: int
    completed: int
    failed: int
    blocked: int
    invalid: int


@dataclass
class ExecutorSandboxMetrics:
    simulations_total: int = 0
    completed: int = 0
    failed: int = 0
    blocked: int = 0
    invalid: int = 0

    def record(self, state: SandboxExecutionStatusV1) -> None:
        self.simulations_total += 1
        self.completed += int(state is SandboxExecutionStatusV1.SANDBOX_COMPLETED)
        self.failed += int(state is SandboxExecutionStatusV1.SANDBOX_FAILED)
        self.blocked += int(state is SandboxExecutionStatusV1.SANDBOX_BLOCKED)
        self.invalid += int(state is SandboxExecutionStatusV1.SANDBOX_INVALID)

    def snapshot(self) -> ExecutorSandboxMetricSnapshotV1:
        return ExecutorSandboxMetricSnapshotV1(**vars(self))
