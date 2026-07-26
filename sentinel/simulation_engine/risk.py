"""Risk reuse from Recommendation Engine without parallel scoring."""

from sentinel.contracts import (
    SimulationOutcomeV1,
    SimulationRiskLevelV1,
)
from sentinel.recommendation_engine import RiskLevel

_RISK_MAP = {
    RiskLevel.LOW: (
        SimulationRiskLevelV1.LOW,
        SimulationOutcomeV1.SIMULATION_SAFE,
    ),
    RiskLevel.MEDIUM: (
        SimulationRiskLevelV1.MEDIUM,
        SimulationOutcomeV1.SIMULATION_WARNING,
    ),
    RiskLevel.HIGH: (
        SimulationRiskLevelV1.HIGH,
        SimulationOutcomeV1.SIMULATION_HIGH_RISK,
    ),
    RiskLevel.CRITICAL: (
        SimulationRiskLevelV1.CRITICAL,
        SimulationOutcomeV1.SIMULATION_BLOCKED,
    ),
}


def inherited_risk(
    risk: RiskLevel,
) -> tuple[SimulationRiskLevelV1, SimulationOutcomeV1]:
    return _RISK_MAP[risk]
