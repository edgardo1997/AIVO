"""Public interfaces for persistent, non-authoritative safety state."""

from importlib import import_module

__all__ = [
    "AUTHORITY_SAFETY_LAYER_ENABLED",
    "AuthorityAuditStore",
    "AuthoritySafetyControl",
    "AuthoritySafetyController",
    "AuthoritySafetyMetrics",
    "AuthoritySafetyReport",
    "AuthoritySafetyStorage",
    "IdempotencyState",
    "PersistentIdempotencyManager",
    "RecoveryManager",
    "RecoveryStatus",
    "SafetyOperationRecord",
]

_EXPORTS = {
    "AUTHORITY_SAFETY_LAYER_ENABLED": (
        ".control",
        "AUTHORITY_SAFETY_LAYER_ENABLED",
    ),
    "AuthorityAuditStore": (".audit_store", "AuthorityAuditStore"),
    "AuthoritySafetyControl": (".control", "AuthoritySafetyControl"),
    "AuthoritySafetyController": (".control", "AuthoritySafetyController"),
    "AuthoritySafetyMetrics": (".metrics", "AuthoritySafetyMetrics"),
    "AuthoritySafetyReport": (".report", "AuthoritySafetyReport"),
    "AuthoritySafetyStorage": (".storage", "AuthoritySafetyStorage"),
    "IdempotencyState": (".state", "IdempotencyState"),
    "PersistentIdempotencyManager": (
        ".idempotency",
        "PersistentIdempotencyManager",
    ),
    "RecoveryManager": (".recovery", "RecoveryManager"),
    "RecoveryStatus": (".recovery", "RecoveryStatus"),
    "SafetyOperationRecord": (".state", "SafetyOperationRecord"),
}


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(name)
    module_name, attribute = _EXPORTS[name]
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value
