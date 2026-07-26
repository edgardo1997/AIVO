"""Reuse upstream risk and decisions without independent scoring."""

from sentinel.contracts import (
    ExecutionBoundaryDecisionV1,
    ExecutionPlanStatusV1,
    PolicyEvaluationStatusV1,
    SandboxSimulationStatusV1,
    SimulationRiskLevelV1,
)


def plan_status(
    *,
    errors: tuple[str, ...],
    boundary: ExecutionBoundaryDecisionV1,
    policy: PolicyEvaluationStatusV1,
    sandbox: SandboxSimulationStatusV1,
    risk: SimulationRiskLevelV1,
) -> ExecutionPlanStatusV1:
    if errors:
        return ExecutionPlanStatusV1.PLAN_INVALID
    if (
        boundary
        in {
            ExecutionBoundaryDecisionV1.EXECUTION_BLOCKED,
            ExecutionBoundaryDecisionV1.EXECUTION_INVALID,
        }
        or policy
        in {
            PolicyEvaluationStatusV1.POLICY_BLOCKED,
            PolicyEvaluationStatusV1.POLICY_UNKNOWN,
        }
        or sandbox
        in {
            SandboxSimulationStatusV1.SIMULATION_BLOCKED,
            SandboxSimulationStatusV1.SIMULATION_HIGH_RISK,
        }
        or risk is SimulationRiskLevelV1.CRITICAL
    ):
        return ExecutionPlanStatusV1.PLAN_BLOCKED
    if (
        boundary is ExecutionBoundaryDecisionV1.EXECUTION_REVIEW_REQUIRED
        or policy is PolicyEvaluationStatusV1.POLICY_REVIEW_REQUIRED
        or sandbox is SandboxSimulationStatusV1.SIMULATION_WARNING
        or risk in {SimulationRiskLevelV1.MEDIUM, SimulationRiskLevelV1.HIGH}
    ):
        return ExecutionPlanStatusV1.PLAN_REVIEW_REQUIRED
    return ExecutionPlanStatusV1.PLAN_CREATED
