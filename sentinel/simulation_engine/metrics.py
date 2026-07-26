"""Aggregate simulation counters."""

from dataclasses import dataclass

from sentinel.contracts import (
    DecisionResultV1,
    SimulationOutcomeV1,
)


class SimulationMetricSnapshotV1(DecisionResultV1):
    simulations: int
    safe: int
    warnings: int
    high_risk: int
    blocked: int


@dataclass
class SimulationMetrics:
    simulations: int = 0
    safe: int = 0
    warnings: int = 0
    high_risk: int = 0
    blocked: int = 0

    def record(self, outcome: SimulationOutcomeV1) -> None:
        self.simulations += 1
        self.safe += int(outcome is SimulationOutcomeV1.SIMULATION_SAFE)
        self.warnings += int(outcome is SimulationOutcomeV1.SIMULATION_WARNING)
        self.high_risk += int(outcome is SimulationOutcomeV1.SIMULATION_HIGH_RISK)
        self.blocked += int(outcome is SimulationOutcomeV1.SIMULATION_BLOCKED)

    def snapshot(self) -> SimulationMetricSnapshotV1:
        return SimulationMetricSnapshotV1(**vars(self))
