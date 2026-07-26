"""Human-readable passive sandbox report."""

from .simulation import SandboxEvaluationEnvelopeV1


def render_sandbox_report(result: SandboxEvaluationEnvelopeV1) -> str:
    simulation = result.simulation
    return "\n".join(
        (
            "SENTINEL SANDBOX ENGINE V2 PASSIVE REPORT",
            f"Status: {simulation.status.value}",
            f"Category: {simulation.requested_category.value}",
            f"Impact: {simulation.estimated_impact}",
            f"Rollback predicted: {str(simulation.rollback_available).lower()}",
            f"Risk: {simulation.risk_level.value}",
            "Authority: false",
            "Execution requested: false",
        )
    )
