"""Human-readable representation without decision capability."""

from .orchestrator import ShadowDecisionResultV1


def render_shadow_report(result: ShadowDecisionResultV1) -> str:
    return "\n".join(
        (
            "SENTINEL SHADOW DECISION ORCHESTRATOR REPORT",
            f"Equivalence: {result.comparison.classification.value}",
            f"Confidence: {result.comparison.confidence:.1f}",
            f"Readiness: {result.readiness.status.value}",
            f"Health: {result.health.state.value}",
            "Authority: false",
            "Execution requested: false",
        )
    )
