"""Explicit category matrix for limited scopes."""

from sentinel.contracts import AuthorizationScopeV1, ToolCategoryV1

_SCOPE_CATEGORIES = {
    AuthorizationScopeV1.READ_ONLY: frozenset(
        {
            ToolCategoryV1.FILE_READ,
            ToolCategoryV1.FILE_ANALYSIS,
            ToolCategoryV1.SYSTEM_INFORMATION,
            ToolCategoryV1.PROCESS_INFORMATION,
        }
    ),
    AuthorizationScopeV1.SIMULATION_ONLY: frozenset({ToolCategoryV1.FILE_ANALYSIS}),
    AuthorizationScopeV1.USER_APPROVED_ACTION: frozenset(ToolCategoryV1),
}


def scope_allows(
    scope: AuthorizationScopeV1,
    category: ToolCategoryV1,
) -> bool:
    return category in _SCOPE_CATEGORIES[scope]
