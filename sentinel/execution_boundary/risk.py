"""Deterministic passive boundary classification."""

from sentinel.contracts import (
    ExecutionBoundaryDecisionV1,
    PolicyEvaluationStatusV1,
    SandboxSimulationStatusV1,
    SimulationRiskLevelV1,
    ToolGatewayDecisionValueV1,
)


def classify_boundary(
    *,
    validation_errors: tuple[str, ...],
    gateway_decision: ToolGatewayDecisionValueV1,
    simulation_status: SandboxSimulationStatusV1,
    policy_status: PolicyEvaluationStatusV1,
    risk_level: SimulationRiskLevelV1,
) -> ExecutionBoundaryDecisionV1:
    if validation_errors:
        return ExecutionBoundaryDecisionV1.EXECUTION_INVALID
    if (
        gateway_decision
        in {
            ToolGatewayDecisionValueV1.TOOL_BLOCKED,
            ToolGatewayDecisionValueV1.TOOL_UNKNOWN,
        }
        or simulation_status
        in {
            SandboxSimulationStatusV1.SIMULATION_BLOCKED,
            SandboxSimulationStatusV1.SIMULATION_HIGH_RISK,
        }
        or policy_status
        in {
            PolicyEvaluationStatusV1.POLICY_BLOCKED,
            PolicyEvaluationStatusV1.POLICY_UNKNOWN,
        }
        or risk_level is SimulationRiskLevelV1.CRITICAL
    ):
        return ExecutionBoundaryDecisionV1.EXECUTION_BLOCKED
    if (
        gateway_decision is ToolGatewayDecisionValueV1.TOOL_REQUIRES_REVIEW
        or simulation_status is SandboxSimulationStatusV1.SIMULATION_WARNING
        or policy_status is PolicyEvaluationStatusV1.POLICY_REVIEW_REQUIRED
        or risk_level in {SimulationRiskLevelV1.MEDIUM, SimulationRiskLevelV1.HIGH}
    ):
        return ExecutionBoundaryDecisionV1.EXECUTION_REVIEW_REQUIRED
    return ExecutionBoundaryDecisionV1.EXECUTION_READY
