"""Risk is inherited from simulation; no policy scoring is performed."""

from sentinel.contracts import SimulationResultV1, SimulationRiskLevelV1


def inherited_policy_risk(
    simulation: SimulationResultV1,
) -> SimulationRiskLevelV1:
    return simulation.risk_level
