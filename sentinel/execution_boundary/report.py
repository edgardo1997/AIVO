"""Human-readable passive boundary report."""

from .boundary import ExecutionBoundaryEnvelopeV1


def render_execution_boundary_report(
    envelope: ExecutionBoundaryEnvelopeV1,
) -> str:
    return "\n".join(
        (
            "SENTINEL EXECUTION BOUNDARY V2 REPORT",
            f"Decision: {envelope.decision.decision.value}",
            f"Risk: {envelope.decision.risk_level.value}",
            "Authority: false",
            "Execution requested: false",
        )
    )
