"""Public interfaces for conservative, limited authority migration."""

from importlib import import_module

__all__ = [
    "V2_AUTHORITY_MIGRATION_ENABLED",
    "V2_AUTHORITY_SCOPE",
    "AuthorityAuditLog",
    "AuthorityDecision",
    "AuthorityMigrationController",
    "AuthorityMigrationMetrics",
    "AuthorityMigrationReport",
    "AuthorityMigrationState",
    "AuthorityRouter",
    "AuthoritySelection",
    "FallbackController",
    "MigrationPolicyV1",
    "RoutingContextV1",
]

_EXPORTS = {
    "V2_AUTHORITY_MIGRATION_ENABLED": (
        ".control",
        "V2_AUTHORITY_MIGRATION_ENABLED",
    ),
    "V2_AUTHORITY_SCOPE": (".control", "V2_AUTHORITY_SCOPE"),
    "AuthorityAuditLog": (".audit", "AuthorityAuditLog"),
    "AuthorityDecision": (".router", "AuthorityDecision"),
    "AuthorityMigrationController": (
        ".control",
        "AuthorityMigrationController",
    ),
    "AuthorityMigrationMetrics": (".metrics", "AuthorityMigrationMetrics"),
    "AuthorityMigrationReport": (".report", "AuthorityMigrationReport"),
    "AuthorityMigrationState": (".control", "AuthorityMigrationState"),
    "AuthorityRouter": (".router", "AuthorityRouter"),
    "AuthoritySelection": (".router", "AuthoritySelection"),
    "FallbackController": (".fallback", "FallbackController"),
    "MigrationPolicyV1": (".migration_policy", "MigrationPolicyV1"),
    "RoutingContextV1": (".router", "RoutingContextV1"),
}


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(name)
    module_name, attribute = _EXPORTS[name]
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value
