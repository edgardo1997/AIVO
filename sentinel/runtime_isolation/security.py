"""Closed capability allow/block lists."""

ALLOWED_CAPABILITIES = (
    "filesystem_read",
    "simulation",
    "telemetry",
)

BLOCKED_CAPABILITIES = (
    "execute_command",
    "modify_system",
    "network_admin",
    "process_control",
    "persistent_write",
)
