"""Explicit limited-scope validation."""

from sentinel.contracts import AuthorizationScopeV1

ALLOWED_SCOPES = frozenset(
    {
        AuthorizationScopeV1.READ_ONLY,
        AuthorizationScopeV1.SIMULATION_ONLY,
        AuthorizationScopeV1.USER_APPROVED_ACTION,
    }
)


def validate_scope(scope: AuthorizationScopeV1) -> None:
    if scope not in ALLOWED_SCOPES:
        raise ValueError("authorization scope is not permitted")
