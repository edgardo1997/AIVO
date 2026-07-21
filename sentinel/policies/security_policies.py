from typing import Any, Dict, Optional
from fnmatch import fnmatch

from sentinel.core.policy import Policy, PolicyEffect, PolicyResult
from .loader import load_or_default, PolicyStore

EFFECT_MAP = {
    "allow": PolicyEffect.ALLOW,
    "deny": PolicyEffect.DENY,
    "require_confirm": PolicyEffect.REQUIRE_CONFIRM,
}


def _load_security_config() -> Dict[str, Any]:
    return load_or_default(
        "security.yaml",
        default_factory=lambda: {
            "permission_levels": {
                "view": {"write": "deny", "read": "allow", "dangerous": "deny"},
                "confirm": {"write": "allow", "read": "allow", "dangerous": "require_confirm"},
                "auto": {"write": "allow", "read": "allow", "dangerous": "require_confirm"},
                "admin": {"write": "allow", "read": "allow", "dangerous": "allow"},
            },
            "dangerous_tools": [
                "executor.command",
                "executor.kill",
                "executor.launch",
                "filesystem.write",
                "filesystem.delete",
                "permissions.set_level",
                "permissions.emergency",
                "permissions.confirm",
                "fleet.generate_pairing",
                "fleet.revoke_pairing",
                "fleet.toggle_remote",
                "plugins.load",
                "plugins.unload",
                "plugins.reload",
                "plugins.toggle",
                "plugins.create",
            ],
        },
    )


def _load_levels():
    config = _load_security_config()
    raw = config.get("permission_levels", {})
    levels = {}
    for name, rules in raw.items():
        levels[name] = {action: EFFECT_MAP.get(effect, PolicyEffect.DENY) for action, effect in rules.items()}
    return levels


def _load_dangerous_tools():
    config = _load_security_config()
    return set(config.get("dangerous_tools", []))


LEVELS = _load_levels()
DANGEROUS_TOOLS = _load_dangerous_tools()


def _reload_security():
    global LEVELS, DANGEROUS_TOOLS
    LEVELS = _load_levels()
    DANGEROUS_TOOLS = _load_dangerous_tools()


PolicyStore.get_instance().on_reload(_reload_security)


class PermissionLevelPolicy(Policy):
    def __init__(self, get_level, is_confirmed=None):
        self._get_level = get_level
        self._is_confirmed = is_confirmed

    def policy_id(self) -> str:
        return "permission_level"

    def description(self) -> str:
        return "Maps 4 permission levels (view/confirm/auto/admin) to allow/deny/confirm decisions"

    async def evaluate(
        self,
        tool_id: str,
        params: Dict[str, Any],
        context: Dict[str, Any],
    ) -> PolicyResult:
        level = self._get_level()
        rules = LEVELS.get(level, LEVELS.get("view", {}))

        is_dangerous = any(d in tool_id for d in DANGEROUS_TOOLS)
        is_write = ".write" in tool_id or ".delete" in tool_id or ".create" in tool_id
        is_read = not is_write and (
            ".read" in tool_id or ".list" in tool_id or ".search" in tool_id or ".info" in tool_id
        )

        if is_dangerous:
            effect = rules.get("dangerous", PolicyEffect.DENY)
        elif is_write:
            effect = rules.get("write", PolicyEffect.DENY)
        elif is_read:
            effect = rules.get("read", PolicyEffect.DENY)
        else:
            effect = rules.get("read", PolicyEffect.DENY)

        if effect == PolicyEffect.REQUIRE_CONFIRM:
            grant = context.get("_confirmation_grant") or {}
            identity = context.get("identity") or {}
            if grant.get("tool_id") == tool_id and grant.get("user_id") == identity.get("user_id"):
                return PolicyResult(
                    effect=PolicyEffect.ALLOW,
                    policy_id=self.policy_id(),
                    reason=f"Single-use confirmation '{grant.get('action_id')}' accepted",
                    context={"level": level, "confirmed": True, "action_id": grant.get("action_id")},
                )
            if params.get("confirmed") and params.get("action_id"):
                if self._is_confirmed and self._is_confirmed(params["action_id"]):
                    return PolicyResult(
                        effect=PolicyEffect.ALLOW,
                        policy_id=self.policy_id(),
                        reason=f"Action '{params['action_id']}' was previously confirmed",
                        context={"level": level, "confirmed": True},
                    )

        return PolicyResult(
            effect=effect,
            policy_id=self.policy_id(),
            reason=f"Permission level '{level}': {effect.value} for tool '{tool_id}'",
            context={"level": level, "tool_id": tool_id, "dangerous": is_dangerous},
        )


class IdentityPermissionPolicy(Policy):
    def policy_id(self) -> str:
        return "identity_permissions"

    def description(self) -> str:
        return "Requires an authenticated identity with every permission requested by a tool"

    async def evaluate(
        self,
        tool_id: str,
        params: Dict[str, Any],
        context: Dict[str, Any],
    ) -> PolicyResult:
        identity = context.get("identity") or {}
        required = set(context.get("required_permissions") or [])
        granted = set(identity.get("permissions") or []) if isinstance(identity, dict) else set()
        if not isinstance(identity, dict) or not identity.get("is_authenticated"):
            return PolicyResult(
                effect=PolicyEffect.DENY,
                policy_id=self.policy_id(),
                reason="Authenticated identity is required",
            )
        missing = sorted(required - granted) if "*" not in granted else []
        if missing:
            return PolicyResult(
                effect=PolicyEffect.DENY,
                policy_id=self.policy_id(),
                reason=f"Identity lacks permissions: {missing}",
                context={"user_id": identity.get("user_id"), "missing": missing},
            )
        return PolicyResult(
            effect=PolicyEffect.ALLOW,
            policy_id=self.policy_id(),
            reason="Identity permissions satisfied",
            context={"user_id": identity.get("user_id")},
        )


class GranularPermissionPolicy(Policy):
    """Applies user/tool/permission rules that can further restrict baseline access."""

    def __init__(self, get_rules):
        self._get_rules = get_rules

    def policy_id(self) -> str:
        return "granular_permissions"

    def description(self) -> str:
        return "User, tool, capability, and path-scoped permission rules"

    async def evaluate(self, tool_id: str, params: Dict[str, Any], context: Dict[str, Any]) -> PolicyResult:
        identity = context.get("identity") or {}
        user_id = identity.get("user_id", "")
        required = context.get("required_permissions") or []
        path = str(params.get("path") or params.get("root") or "")
        matches = []
        for rule in self._get_rules():
            if rule.get("user_id", "*") not in ("*", user_id):
                continue
            if not fnmatch(tool_id, rule.get("tool", "*")):
                continue
            permission = rule.get("permission", "*")
            if permission != "*" and permission not in required:
                continue
            scope = rule.get("path_prefix") or ""
            if scope and not path.lower().startswith(str(scope).lower()):
                continue
            matches.append(rule)
        for effect in ("deny", "require_confirm"):
            matched = next((rule for rule in matches if rule.get("effect") == effect), None)
            if matched:
                grant = context.get("_confirmation_grant") or {}
                if effect == "require_confirm" and grant.get("tool_id") == tool_id and grant.get("user_id") == user_id:
                    continue
                return PolicyResult(
                    PolicyEffect.DENY if effect == "deny" else PolicyEffect.REQUIRE_CONFIRM,
                    self.policy_id(),
                    f"Granular rule '{matched.get('id')}' -> {effect}",
                    {"rule": matched},
                )
        return PolicyResult(PolicyEffect.ALLOW, self.policy_id(), "No restrictive granular rule matched")


class EmergencyStopPolicy(Policy):
    def __init__(self, is_emergency_stop: Optional[callable] = None):
        self._is_emergency_stop = is_emergency_stop or (lambda: False)

    def policy_id(self) -> str:
        return "emergency_stop"

    def description(self) -> str:
        return "Global kill switch that denies all execution when active"

    async def evaluate(
        self,
        tool_id: str,
        params: Dict[str, Any],
        context: Dict[str, Any],
    ) -> PolicyResult:
        if self._is_emergency_stop():
            if tool_id == "permissions.status":
                return PolicyResult(
                    effect=PolicyEffect.ALLOW,
                    policy_id=self.policy_id(),
                    reason="Emergency stop status remains observable",
                    context={"emergency_stop": True},
                )
            if tool_id == "permissions.emergency" and params.get("action") == "resume":
                return PolicyResult(
                    effect=PolicyEffect.ALLOW,
                    policy_id=self.policy_id(),
                    reason="Emergency stop allows permissions.emergency resume",
                    context={"emergency_stop": True},
                )
            return PolicyResult(
                effect=PolicyEffect.DENY,
                policy_id=self.policy_id(),
                reason="Emergency stop is active. All execution denied.",
                context={"emergency_stop": True},
            )
        return PolicyResult(
            effect=PolicyEffect.ALLOW,
            policy_id=self.policy_id(),
            reason="Emergency stop not active",
        )
