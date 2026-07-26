"""Human-readable passive execution plan report."""

from .planner import ExecutionPlannerEnvelopeV1


def render_execution_plan_report(envelope: ExecutionPlannerEnvelopeV1) -> str:
    return "\n".join(
        (
            "SENTINEL EXECUTION PLANNER V2 REPORT",
            f"Status: {envelope.plan.status.value}",
            f"Steps: {len(envelope.plan.steps)}",
            "Authority: false",
            "Execution requested: false",
        )
    )
