"""Human-readable representation of a hypothetical result."""

from .simulator import SimulationEnvelopeV1


def render_simulation_report(envelope: SimulationEnvelopeV1) -> str:
    result = envelope.simulation
    return "\n".join(
        (
            "SENTINEL V2 PASSIVE SIMULATION REPORT",
            f"Result: {result.result_type.value}",
            f"Impact: {result.impact_summary}",
            f"Risk: {result.risk_level.value}",
            f"Rollback available: {str(result.rollback_available).lower()}",
            f"Confidence: {result.confidence:.2f}",
            "Authority: false",
            "Execution requested: false",
        )
    )
