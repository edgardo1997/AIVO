"""Human-readable authorization status without execution semantics."""

from .authorization import AuthorizationOperationResultV1


def render_authorization_report(
    result: AuthorizationOperationResultV1,
) -> str:
    grant = result.grant
    return "\n".join(
        (
            "SENTINEL V2 PASSIVE AUTHORIZATION REPORT",
            f"Status: {grant.status.value}",
            f"Scope: {grant.scope.value}",
            f"Action: {grant.allowed_action.value}",
            f"Expires: {grant.expires_at.isoformat()}",
            "Authority: false",
            "Execution requested: false",
        )
    )
