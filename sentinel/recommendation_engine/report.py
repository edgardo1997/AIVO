"""Report rendering only; it cannot create recommendations."""

from .engine import RecommendationResultV1


def render_recommendation_report(result: RecommendationResultV1) -> str:
    explanation = result.explanation
    return "\n".join(
        (
            "SENTINEL V2 RECOMMENDATION REPORT",
            f"Recommendation: {result.evaluation.recommendation.value}",
            f"Reason: {explanation.reason}",
            f"Confidence: {explanation.confidence:.2f}",
            f"Risk: {explanation.risk.value}",
            f"Health: {explanation.health.value}",
            f"Readiness: {explanation.readiness.value}",
            "Authority: false",
            "Execution requested: false",
        )
    )
