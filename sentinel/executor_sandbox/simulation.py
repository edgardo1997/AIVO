"""Deterministic traversal of descriptive plan step contracts."""

from sentinel.contracts import (
    ExecutionPlanResultV1,
    SimulatedExecutionStepV1,
)


def simulate_steps(
    plan: ExecutionPlanResultV1,
    *,
    blocked: bool,
) -> tuple[SimulatedExecutionStepV1, ...]:
    return tuple(
        SimulatedExecutionStepV1(
            step_id=step.step_id,
            sequence=step.sequence,
            expected_state=step.verification,
            completed=not blocked,
        )
        for step in plan.steps
    )
