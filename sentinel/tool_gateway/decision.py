"""Deterministic passive gateway decision selection."""

from sentinel.contracts import (
    AuthorizationScopeV1,
    PolicyEvaluationStatusV1,
    SimulationRiskLevelV1,
    ToolGatewayDecisionValueV1,
)

from .request import ToolRequestV1
from .risk import risk_decision
from .scope import scope_allows


def decide(
    *,
    request: ToolRequestV1,
    granted_scope: AuthorizationScopeV1,
    risk: SimulationRiskLevelV1,
    policy_status: PolicyEvaluationStatusV1,
    origin_errors: tuple[str, ...],
) -> tuple[ToolGatewayDecisionValueV1, tuple[str, ...]]:
    if origin_errors:
        return ToolGatewayDecisionValueV1.TOOL_BLOCKED, origin_errors
    if request.requested_scope is not granted_scope:
        return (
            ToolGatewayDecisionValueV1.TOOL_BLOCKED,
            ("SCOPE_ESCALATION",),
        )
    if not scope_allows(granted_scope, request.requested_tool_category):
        return (
            ToolGatewayDecisionValueV1.TOOL_BLOCKED,
            ("CATEGORY_OUTSIDE_SCOPE",),
        )
    if policy_status is PolicyEvaluationStatusV1.POLICY_BLOCKED:
        return (
            ToolGatewayDecisionValueV1.TOOL_BLOCKED,
            ("POLICY_BLOCKED",),
        )
    if policy_status is PolicyEvaluationStatusV1.POLICY_UNKNOWN:
        return (
            ToolGatewayDecisionValueV1.TOOL_UNKNOWN,
            ("POLICY_UNKNOWN",),
        )
    selected = risk_decision(
        risk=risk,
        category=request.requested_tool_category,
    )
    reason = {
        ToolGatewayDecisionValueV1.TOOL_ALLOWED: "PASSIVE_POLICY_COMPATIBLE",
        ToolGatewayDecisionValueV1.TOOL_REQUIRES_REVIEW: "REVIEW_REQUIRED",
        ToolGatewayDecisionValueV1.TOOL_BLOCKED: "CRITICAL_RISK",
    }[selected]
    return selected, (reason,)
