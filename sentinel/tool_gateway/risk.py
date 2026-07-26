"""Risk decisions inherited from passive policy evaluation."""

from sentinel.contracts import (
    SimulationRiskLevelV1,
    ToolCategoryV1,
    ToolGatewayDecisionValueV1,
)


def risk_decision(
    *,
    risk: SimulationRiskLevelV1,
    category: ToolCategoryV1,
) -> ToolGatewayDecisionValueV1:
    if risk is SimulationRiskLevelV1.CRITICAL:
        return ToolGatewayDecisionValueV1.TOOL_BLOCKED
    if risk is SimulationRiskLevelV1.HIGH:
        return ToolGatewayDecisionValueV1.TOOL_REQUIRES_REVIEW
    if category is ToolCategoryV1.USER_APPROVED_CHANGE:
        return ToolGatewayDecisionValueV1.TOOL_REQUIRES_REVIEW
    return ToolGatewayDecisionValueV1.TOOL_ALLOWED
