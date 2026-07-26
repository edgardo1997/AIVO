"""In-memory sandbox simulation metrics."""

from dataclasses import dataclass

from sentinel.contracts import (
    DecisionResultV1,
    SandboxSimulationStatusV1,
)


class SandboxMetricSnapshotV1(DecisionResultV1):
    simulations_total: int
    safe: int
    warning: int
    high_risk: int
    blocked: int


@dataclass
class SandboxMetrics:
    simulations_total: int = 0
    safe: int = 0
    warning: int = 0
    high_risk: int = 0
    blocked: int = 0

    def record(self, status: SandboxSimulationStatusV1) -> None:
        self.simulations_total += 1
        self.safe += int(status is SandboxSimulationStatusV1.SIMULATION_SAFE)
        self.warning += int(status is SandboxSimulationStatusV1.SIMULATION_WARNING)
        self.high_risk += int(status is SandboxSimulationStatusV1.SIMULATION_HIGH_RISK)
        self.blocked += int(status is SandboxSimulationStatusV1.SIMULATION_BLOCKED)

    def snapshot(self) -> SandboxMetricSnapshotV1:
        return SandboxMetricSnapshotV1(**vars(self))
