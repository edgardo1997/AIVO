"""Strict permission model for the Sentinel Plugin SDK.

A plugin is a third-party application with access to the brains and hands of
the system. Permissions are therefore explicit, evaluated by risk and always
gated behind a user approval token. No permission is ever granted implicitly.
"""

from __future__ import annotations

import time as time_mod
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

RISK_LOW = "low"
RISK_MEDIUM = "medium"
RISK_HIGH = "high"
RISK_CRITICAL = "critical"
RISK_LEVELS = (RISK_LOW, RISK_MEDIUM, RISK_HIGH, RISK_CRITICAL)

# The complete catalogue of permissions a plugin may request.
# Each permission is grouped and carries an explicit risk rating.
PERMISSION_CATALOG: Dict[str, Dict[str, Any]] = {
    # System
    "system.read": {"group": "system", "risk": RISK_LOW, "description": "Read system information (CPU, RAM, disk, uptime)"},
    "system.modify": {"group": "system", "risk": RISK_CRITICAL, "description": "Change system configuration"},
    "process.manage": {"group": "system", "risk": RISK_CRITICAL, "description": "List, suspend or terminate processes"},
    # Files
    "filesystem.read": {"group": "files", "risk": RISK_LOW, "description": "Read files and directories"},
    "filesystem.write": {"group": "files", "risk": RISK_MEDIUM, "description": "Create, modify or delete files"},
    # Applications
    "application.launch": {"group": "app", "risk": RISK_MEDIUM, "description": "Launch applications"},
    "application.control": {"group": "app", "risk": RISK_HIGH, "description": "Control running applications"},
    # Network
    "network.request": {"group": "network", "risk": RISK_HIGH, "description": "Make outbound network requests"},
    # AI
    "model.request": {"group": "ai", "risk": RISK_MEDIUM, "description": "Request model inference"},
    "memory.access": {"group": "ai", "risk": RISK_HIGH, "description": "Read or write Sentinel memory"},
}

_DEFAULT_TOKEN_TTL_SECONDS = 6 * 3600


@dataclass
class PermissionToken:
    plugin_id: str
    permissions: frozenset
    granted_at: float
    expires_at: float
    token_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    approval_note: str = "user_approved"

    def is_valid(self, now: Optional[float] = None) -> bool:
        instant = now if now is not None else time_mod.time()
        return self.expires_at > instant

    def to_dict(self) -> Dict[str, Any]:
        return {
            "token_id": self.token_id,
            "plugin_id": self.plugin_id,
            "permissions": sorted(self.permissions),
            "granted_at": self.granted_at,
            "expires_at": self.expires_at,
            "approval_note": self.approval_note,
        }


@dataclass
class ApprovalRecord:
    plugin_id: str
    permissions: List[str]
    granted_at: float
    token_id: str
    risk: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plugin_id": self.plugin_id,
            "permissions": list(self.permissions),
            "granted_at": self.granted_at,
            "token_id": self.token_id,
            "risk": self.risk,
        }


class PermissionDeniedError(PermissionError):
    pass


def evaluate_risk(permissions) -> str:
    """Return the highest risk level present in a set of permissions."""
    highest = RISK_LOW
    for perm in permissions:
        meta = PERMISSION_CATALOG.get(perm, {})
        level = meta.get("risk", RISK_LOW)
        if RISK_LEVELS.index(level) > RISK_LEVELS.index(highest):
            highest = level
    return highest


def requires_user_approval(permissions) -> bool:
    """Any request with at least medium risk needs explicit user approval."""
    return evaluate_risk(permissions) in (RISK_MEDIUM, RISK_HIGH, RISK_CRITICAL)


def unknown_permissions(permissions) -> List[str]:
    return sorted(set(permissions) - set(PERMISSION_CATALOG))


class PluginPermissionManager:
    """Evaluates risk, records approvals and issues scoped permission tokens."""

    def __init__(self, storage: Optional[Any] = None, clock=None) -> None:
        self._storage = storage
        self._clock = clock or time_mod.time
        self._tokens: Dict[str, PermissionToken] = {}
        self._approvals: List[ApprovalRecord] = []
        self._restore()

    # --- persistence (optional) ---

    def _restore(self) -> None:
        if self._storage is None:
            return
        try:
            state = self._storage.config_get_json("plugin_permission_tokens", {})
            for record in state.get("tokens", []):
                token = PermissionToken(
                    plugin_id=record["plugin_id"],
                    permissions=frozenset(record.get("permissions", [])),
                    granted_at=float(record.get("granted_at", 0)),
                    expires_at=float(record.get("expires_at", 0)),
                    token_id=record.get("token_id", ""),
                    approval_note=record.get("approval_note", "restored"),
                )
                self._tokens[token.plugin_id] = token
            for record in state.get("approvals", []):
                self._approvals.append(
                    ApprovalRecord(
                        plugin_id=record["plugin_id"],
                        permissions=list(record.get("permissions", [])),
                        granted_at=float(record.get("granted_at", 0)),
                        token_id=record.get("token_id", ""),
                        risk=record.get("risk", RISK_LOW),
                    )
                )
        except Exception:
            self._tokens = {}
            self._approvals = []

    def _persist(self) -> None:
        if self._storage is None:
            return
        try:
            self._storage.config_set_json(
                "plugin_permission_tokens",
                {
                    "tokens": [t.to_dict() for t in self._tokens.values()],
                    "approvals": [a.to_dict() for a in self._approvals[-100:]],
                },
            )
        except Exception as exc:
            raise RuntimeError("Failed to persist plugin permission state") from exc

    # --- evaluation ---

    def validate_manifest_permissions(self, permissions) -> List[str]:
        return unknown_permissions(permissions)

    def evaluate(self, permissions) -> Dict[str, Any]:
        perms = list(permissions)
        unknown = unknown_permissions(perms)
        risk = evaluate_risk(perms)
        return {
            "permissions": sorted(perms),
            "risk": risk,
            "requires_approval": requires_user_approval(perms),
            "critical": risk == RISK_CRITICAL,
            "unknown": unknown,
        }

    # --- token lifecycle ---

    def grant(self, plugin_id: str, permissions, ttl_seconds: int = _DEFAULT_TOKEN_TTL_SECONDS, now: Optional[float] = None) -> PermissionToken:
        """Issue an approved token for a plugin (user consent already obtained)."""
        perms = frozenset(permissions)
        instant = now if now is not None else self._clock()
        token = PermissionToken(
            plugin_id=plugin_id,
            permissions=perms,
            granted_at=instant,
            expires_at=instant + max(60, int(ttl_seconds)),
        )
        previous_token = self._tokens.get(plugin_id)
        approval_count = len(self._approvals)
        self._tokens[plugin_id] = token
        self._approvals.append(
            ApprovalRecord(plugin_id=plugin_id, permissions=sorted(perms), granted_at=instant, token_id=token.token_id, risk=evaluate_risk(perms))
        )
        try:
            self._persist()
        except Exception:
            if previous_token is None:
                self._tokens.pop(plugin_id, None)
            else:
                self._tokens[plugin_id] = previous_token
            del self._approvals[approval_count:]
            raise
        return token

    def revoke(self, plugin_id: str) -> bool:
        removed = self._tokens.pop(plugin_id, None)
        if removed is not None:
            try:
                self._persist()
            except Exception:
                self._tokens[plugin_id] = removed
                raise
        return removed is not None

    def token_for(self, plugin_id: str, now: Optional[float] = None) -> Optional[PermissionToken]:
        token = self._tokens.get(plugin_id)
        if token is None:
            return None
        if not token.is_valid(now=now if now is not None else self._clock()):
            return None
        return token

    def has_permission(self, plugin_id: str, permission: str, now: Optional[float] = None) -> bool:
        token = self.token_for(plugin_id, now=now)
        return token is not None and permission in token.permissions

    def require_permission(self, plugin_id: str, permission: str, now: Optional[float] = None) -> None:
        if not self.has_permission(plugin_id, permission, now=now):
            raise PermissionDeniedError(f"plugin '{plugin_id}' lacks permission '{permission}'")

    def approved_permissions(self, plugin_id: str) -> List[str]:
        token = self.token_for(plugin_id)
        return sorted(token.permissions) if token else []

    def approvals(self) -> List[Dict[str, Any]]:
        return [a.to_dict() for a in self._approvals]
