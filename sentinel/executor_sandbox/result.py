"""Deterministic sandbox final-state selection."""

from sentinel.contracts import (
    ExecutionPlanStatusV1,
    PolicyEvaluationStatusV1,
    SandboxExecutionStatusV1,
)


def final_state(
    *,
    errors: tuple[str, ...],
    plan_status: ExecutionPlanStatusV1,
    policy_status: PolicyEvaluationStatusV1,
) -> SandboxExecutionStatusV1:
    if errors:
        return SandboxExecutionStatusV1.SANDBOX_INVALID
    if plan_status in {
        ExecutionPlanStatusV1.PLAN_BLOCKED,
        ExecutionPlanStatusV1.PLAN_INVALID,
    } or policy_status in {
        PolicyEvaluationStatusV1.POLICY_BLOCKED,
        PolicyEvaluationStatusV1.POLICY_UNKNOWN,
    }:
        return SandboxExecutionStatusV1.SANDBOX_BLOCKED
    return SandboxExecutionStatusV1.SANDBOX_COMPLETED
