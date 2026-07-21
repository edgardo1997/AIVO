from typing import Any, Dict, FrozenSet, List, Optional
from fnmatch import fnmatch

from sentinel.core.policy import Policy, PolicyEffect, PolicyResult

# ── Role Capability Matrix ──────────────────────────────────────────────────
# Maps each role to allowed tool patterns, write patterns, and dangerous tools.
# The strictest grant wins: if a tool matches none of a role's patterns → DENY.

ADMIN_TOOLS: FrozenSet[str] = frozenset({"*"})
ADMIN_WRITE: FrozenSet[str] = frozenset({"*"})
ADMIN_DANGEROUS: FrozenSet[str] = frozenset({"*"})

USER_READ: FrozenSet[str] = frozenset({
    "system.*", "filesystem.read", "filesystem.list", "filesystem.search",
    "ai.*", "audit.*", "profile.*", "agent.*", "fleet.status", "fleet.list",
    "plugin.list", "plugin.templates", "permissions.status",
})
USER_WRITE: FrozenSet[str] = frozenset({
    "filesystem.write", "profile.*", "ai.config",
})
USER_DANGEROUS: FrozenSet[str] = frozenset({
    "executor.command", "executor.launch", "executor.kill",
    "executor.restart", "filesystem.delete",
})

VIEWER_TOOLS: FrozenSet[str] = frozenset({
    "system.*", "filesystem.read", "filesystem.list", "filesystem.search",
    "ai.chat", "ai.analyze", "audit.*", "profile.read",
    "fleet.status", "fleet.list", "plugin.list", "permissions.status",
})
VIEWER_WRITE: FrozenSet[str] = frozenset()
VIEWER_DANGEROUS: FrozenSet[str] = frozenset()

# Critical tools that require admin role regardless of permission level.
CRITICAL_TOOLS: FrozenSet[str] = frozenset({
    "permissions.set_level", "permissions.emergency", "permissions.confirm",
    "permissions.blocklist", "permissions.remove_blocklist",
    "fleet.generate_pairing", "fleet.revoke_pairing", "fleet.toggle_remote",
    "fleet.delete_device",
    "plugins.load", "plugins.unload", "plugins.reload", "plugins.toggle",
    "plugins.create", "plugins.install_url", "plugins.install_zip",
    "vault.*",
    "policies.reload",
    "admin.config_set", "admin.config_delete", "admin.backup",
    "permissions.add_rule", "permissions.remove_rule",
})


class RoleCapabilityMatrix:
    """Central capability matrix that maps roles to allowed tool patterns."""

    def __init__(self) -> None:
        self._matrix: Dict[str, Dict[str, FrozenSet[str]]] = {
            "admin": {
                "read": ADMIN_TOOLS,
                "write": ADMIN_WRITE,
                "dangerous": ADMIN_DANGEROUS,
            },
            "user": {
                "read": USER_READ,
                "write": USER_WRITE,
                "dangerous": USER_DANGEROUS,
            },
            "viewer": {
                "read": VIEWER_TOOLS,
                "write": VIEWER_WRITE,
                "dangerous": VIEWER_DANGEROUS,
            },
        }

    def classify_tool(self, tool_id: str) -> str:
        if any(fnmatch(tool_id, p) for p in CRITICAL_TOOLS):
            return "critical"
        # Check non-admin dangerous patterns first
        for p in USER_DANGEROUS:
            if fnmatch(tool_id, p):
                return "dangerous"
        for p in VIEWER_DANGEROUS:
            if fnmatch(tool_id, p):
                return "dangerous"
        # Check write patterns
        for p in USER_WRITE:
            if fnmatch(tool_id, p):
                return "write"
        # Fallback heuristics
        if ".write" in tool_id or ".delete" in tool_id or ".create" in tool_id:
            return "write"
        if ".read" in tool_id or ".list" in tool_id or ".search" in tool_id or ".info" in tool_id:
            return "read"
        return "read"

    def allowed(self, role: str, tool_id: str) -> bool:
        """Check if the given role is allowed to use the given tool."""
        role_caps = self._matrix.get(role)
        if not role_caps:
            return False
        if role == "admin":
            return True
        for category in ("dangerous", "write", "read"):
            for pattern in role_caps.get(category, frozenset()):
                if fnmatch(tool_id, pattern):
                    return True
        return False

    def requires_admin(self, tool_id: str) -> bool:
        return any(fnmatch(tool_id, p) for p in CRITICAL_TOOLS)


class CapabilityMatrixPolicy(Policy):
    """Policy that enforces the role capability matrix.

    Denies tools not in the role's matrix, and requires admin for critical tools.
    """

    def __init__(self, matrix: Optional[RoleCapabilityMatrix] = None):
        self._matrix = matrix or RoleCapabilityMatrix()

    def policy_id(self) -> str:
        return "capability_matrix"

    def description(self) -> str:
        return "Central role capability matrix: viewer/user/admin tool access control"

    async def evaluate(
        self,
        tool_id: str,
        params: Dict[str, Any],
        context: Dict[str, Any],
    ) -> PolicyResult:
        identity = context.get("identity") or {}
        role = identity.get("role", "viewer")

        if self._matrix.requires_admin(tool_id) and role != "admin":
            return PolicyResult(
                effect=PolicyEffect.DENY,
                policy_id=self.policy_id(),
                reason=f"Tool '{tool_id}' requires admin role (current: {role})",
                context={"tool_id": tool_id, "role": role, "required_role": "admin"},
            )

        if not self._matrix.allowed(role, tool_id):
            return PolicyResult(
                effect=PolicyEffect.DENY,
                policy_id=self.policy_id(),
                reason=f"Role '{role}' is not allowed to use tool '{tool_id}'",
                context={"tool_id": tool_id, "role": role},
            )

        return PolicyResult(
            effect=PolicyEffect.ALLOW,
            policy_id=self.policy_id(),
            reason=f"Role '{role}' allowed by capability matrix",
            context={"tool_id": tool_id, "role": role},
        )
