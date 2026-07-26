"""Purely simulated outcome provider with no system capability."""

from enum import Enum


class SimulatedResult(str, Enum):
    SIMULATED_SUCCESS = "SIMULATED_SUCCESS"
    SIMULATED_FAILURE = "SIMULATED_FAILURE"


class SimulatedExecutor:
    def simulate(self, *, should_succeed: bool = True) -> SimulatedResult:
        return SimulatedResult.SIMULATED_SUCCESS if should_succeed else SimulatedResult.SIMULATED_FAILURE
