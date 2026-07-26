"""Immutable description of a hypothetical environment."""

from sentinel.contracts import AuthorizationScopeV1, DecisionResultV1


class HypotheticalEnvironmentV1(DecisionResultV1):
    environment_type: str = "CONTRACT_ONLY"
    affected_scope: AuthorizationScopeV1
    isolated: bool = True
    system_access: bool = False


def hypothetical_environment(
    scope: AuthorizationScopeV1,
) -> HypotheticalEnvironmentV1:
    return HypotheticalEnvironmentV1(affected_scope=scope)
