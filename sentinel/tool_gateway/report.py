"""Human-readable passive gateway report."""

from .gateway import ToolGatewayEvaluationEnvelopeV1


def render_gateway_report(result: ToolGatewayEvaluationEnvelopeV1) -> str:
    decision = result.decision
    return "\n".join(
        (
            "SENTINEL TOOL GATEWAY V2 PASSIVE REPORT",
            f"Decision: {decision.decision.value}",
            f"Category: {decision.requested_tool_category.value}",
            f"Scope: {decision.scope.value}",
            f"Risk: {decision.risk_level.value}",
            f"Reasons: {', '.join(result.reason_codes)}",
            "Authority: false",
            "Execution requested: false",
        )
    )
