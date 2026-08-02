"""Sentinel Plugin SDK.

A stable, strictly validated API for third-party extensions. Plugins declare
what they need (permissions, events, capabilities) and the SDK enforces the
boundaries so the Sentinel core never changes to accommodate a plugin.
"""

from .manifest import (
    CAPABILITIES,
    DEFAULT_ENTRYPOINT,
    EVENT_TYPES,
    SEMVER_PATTERN,
    PluginManifest,
    load_manifest,
    write_manifest,
)
from .plugin_base import PluginContext, SentinelPlugin
from .permission import (
    PERMISSION_CATALOG,
    RISK_LEVELS,
    ApprovalRecord,
    PermissionDeniedError,
    PermissionToken,
    PluginPermissionManager,
    evaluate_risk,
    requires_user_approval,
    unknown_permissions,
)
from .lifecycle import (
    STATE_ACTIVE,
    STATE_DEACTIVATED,
    STATE_ERROR,
    STATE_EXECUTING,
    STATE_INSTALLED,
    STATE_PERMISSION_REVIEW,
    STATE_VALIDATED,
    LifecycleError,
    PluginLifecycle,
)
from .registry import PluginRecord, PluginRegistry
from .events import PluginEvent, PluginEventBus, UnknownEventError
from .validator import calculate_checksum, validate_plugin

__all__ = [
    "CAPABILITIES",
    "DEFAULT_ENTRYPOINT",
    "EVENT_TYPES",
    "SEMVER_PATTERN",
    "PluginManifest",
    "load_manifest",
    "write_manifest",
    "PluginContext",
    "SentinelPlugin",
    "PERMISSION_CATALOG",
    "RISK_LEVELS",
    "ApprovalRecord",
    "PermissionDeniedError",
    "PermissionToken",
    "PluginPermissionManager",
    "evaluate_risk",
    "requires_user_approval",
    "unknown_permissions",
    "STATE_ACTIVE",
    "STATE_DEACTIVATED",
    "STATE_ERROR",
    "STATE_EXECUTING",
    "STATE_INSTALLED",
    "STATE_PERMISSION_REVIEW",
    "STATE_VALIDATED",
    "LifecycleError",
    "PluginLifecycle",
    "PluginRecord",
    "PluginRegistry",
    "PluginEvent",
    "PluginEventBus",
    "UnknownEventError",
    "calculate_checksum",
    "validate_plugin",
]
