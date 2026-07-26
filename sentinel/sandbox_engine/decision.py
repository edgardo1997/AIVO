"""Deterministic sandbox status inherited from gateway risk."""

from sentinel.contracts import (
    SandboxSimulationStatusV1,
    SimulationRiskLevelV1,
    ToolGatewayDecisionValueV1,
)


def simulation_status(
    *,
    gateway_decision: ToolGatewayDecisionValueV1,
    risk: SimulationRiskLevelV1,
    validation_errors: tuple[str, ...],
) -> SandboxSimulationStatusV1:
    if (
        validation_errors
        or gateway_decision
        in {
            ToolGatewayDecisionValueV1.TOOL_BLOCKED,
            ToolGatewayDecisionValueV1.TOOL_UNKNOWN,
        }
        or risk is SimulationRiskLevelV1.CRITICAL
    ):
        return SandboxSimulationStatusV1.SIMULATION_BLOCKED
    if risk is SimulationRiskLevelV1.HIGH:
        return SandboxSimulationStatusV1.SIMULATION_HIGH_RISK
    if risk is SimulationRiskLevelV1.MEDIUM or gateway_decision is ToolGatewayDecisionValueV1.TOOL_REQUIRES_REVIEW:
        return SandboxSimulationStatusV1.SIMULATION_WARNING
    return SandboxSimulationStatusV1.SIMULATION_SAFE
