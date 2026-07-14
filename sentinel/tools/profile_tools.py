import logging
from typing import Any, Dict, Optional

from sentinel.core.tool import Tool, ToolResult, ToolSpec
from sentinel.core.user_profile import UserProfileManager, ALLOWED_PROFILE_FIELDS

logger = logging.getLogger(__name__)

_TOOL_CATEGORY = "profile"


class ProfileGetTool(Tool):
    def __init__(self, profile_mgr: UserProfileManager):
        self._mgr = profile_mgr

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="profile.get",
            name="Get Profile",
            description="Get the user profile and all preferences.",
            version="0.1.0",
            category=_TOOL_CATEGORY,
            parameters={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "User ID (defaults to context user)"},
                },
                "required": [],
            },
            required_permissions=["system.read"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        ctx = context or {}
        identity = ctx.get("identity", {})
        user_id = params.get("user_id") or identity.get("user_id")
        if not user_id:
            return ToolResult.fail("user_id is required", tool_id="profile.get")
        profile = self._mgr.get_profile(user_id)
        if profile is None:
            return ToolResult.fail(f"Profile not found: {user_id}", tool_id="profile.get")
        data = profile.to_dict()
        data["preferences"] = self._mgr.get_all_preferences(user_id)
        return ToolResult.ok(data=data, tool_id="profile.get")


class ProfileUpdateTool(Tool):
    def __init__(self, profile_mgr: UserProfileManager):
        self._mgr = profile_mgr

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="profile.update",
            name="Update Profile",
            description="Update profile fields. Allowed: username, display_name, avatar, theme, timezone, locale, bio, tags.",
            version="0.1.0",
            category=_TOOL_CATEGORY,
            parameters={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "User ID (defaults to context user)"},
                    "username": {"type": "string"},
                    "display_name": {"type": "string"},
                    "avatar": {"type": "string"},
                    "theme": {"type": "string"},
                    "timezone": {"type": "string"},
                    "locale": {"type": "string"},
                    "bio": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": [],
            },
            required_permissions=["permissions.admin"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        ctx = context or {}
        identity = ctx.get("identity", {})
        user_id = params.pop("user_id", None) or identity.get("user_id")
        if not user_id:
            return ToolResult.fail("user_id is required", tool_id="profile.update")
        self._mgr.get_or_create_profile(user_id)
        updates = {k: v for k, v in params.items() if k in ALLOWED_PROFILE_FIELDS}
        profile = self._mgr.update_profile(user_id, **updates)
        return ToolResult.ok(data=profile.to_dict(), tool_id="profile.update")


class ProfilePreferenceTool(Tool):
    def __init__(self, profile_mgr: UserProfileManager):
        self._mgr = profile_mgr

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="profile.preference",
            name="Manage Preferences",
            description="Get, set, or delete user preferences. Action: get, set, delete, list.",
            version="0.1.0",
            category=_TOOL_CATEGORY,
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["get", "set", "delete", "list"],
                        "description": "Action to perform",
                    },
                    "user_id": {"type": "string", "description": "User ID (defaults to context user)"},
                    "key": {"type": "string", "description": "Preference key (required for get/set/delete)"},
                    "value": {"description": "Preference value (required for set)"},
                },
                "required": ["action"],
            },
            required_permissions=["permissions.admin"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        ctx = context or {}
        identity = ctx.get("identity", {})
        user_id = params.get("user_id") or identity.get("user_id")
        if not user_id:
            return ToolResult.fail("user_id is required", tool_id="profile.preference")
        action = params.get("action", "list")
        self._mgr.get_or_create_profile(user_id)
        if action == "get":
            key = params.get("key", "")
            if not key:
                return ToolResult.fail("key is required for get", tool_id="profile.preference")
            value = self._mgr.get_preference(user_id, key)
            if value is None:
                return ToolResult.fail(f"Preference '{key}' not found", tool_id="profile.preference")
            return ToolResult.ok(data={"key": key, "value": value}, tool_id="profile.preference")
        if action == "set":
            key = params.get("key", "")
            if not key:
                return ToolResult.fail("key is required for set", tool_id="profile.preference")
            value = params.get("value")
            self._mgr.set_preference(user_id, key, value)
            return ToolResult.ok(data={"key": key, "value": value, "status": "set"}, tool_id="profile.preference")
        if action == "delete":
            key = params.get("key", "")
            if not key:
                return ToolResult.fail("key is required for delete", tool_id="profile.preference")
            self._mgr.delete_preference(user_id, key)
            return ToolResult.ok(data={"key": key, "status": "deleted"}, tool_id="profile.preference")
        prefs = self._mgr.get_all_preferences(user_id)
        return ToolResult.ok(data={"preferences": prefs, "count": len(prefs)}, tool_id="profile.preference")


class ProfileExportTool(Tool):
    def __init__(self, profile_mgr: UserProfileManager):
        self._mgr = profile_mgr

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="profile.export",
            name="Export Profile",
            description="Export the user profile and all preferences as JSON.",
            version="0.1.0",
            category=_TOOL_CATEGORY,
            parameters={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "User ID (defaults to context user)"},
                },
                "required": [],
            },
            required_permissions=["system.read"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        ctx = context or {}
        identity = ctx.get("identity", {})
        user_id = params.get("user_id") or identity.get("user_id")
        if not user_id:
            return ToolResult.fail("user_id is required", tool_id="profile.export")
        data = self._mgr.export_profile(user_id)
        return ToolResult.ok(data=data, tool_id="profile.export")


class ProfilePresetTool(Tool):
    def __init__(self, profile_mgr: UserProfileManager):
        self._mgr = profile_mgr

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="profile.preset",
            name="Manage Profile Presets",
            description="Save, apply, list, or delete profile configuration presets. Action: save, apply, list, delete.",
            version="0.1.0",
            category=_TOOL_CATEGORY,
            parameters={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["save", "apply", "list", "delete"], "description": "Action"},
                    "user_id": {"type": "string", "description": "User ID (defaults to context user)"},
                    "preset_name": {"type": "string", "description": "Preset name (required for save/apply/delete)"},
                    "description": {"type": "string", "description": "Preset description (optional, for save)"},
                },
                "required": ["action"],
            },
            required_permissions=["permissions.admin"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        ctx = context or {}
        identity = ctx.get("identity", {})
        user_id = params.get("user_id") or identity.get("user_id")
        if not user_id:
            return ToolResult.fail("user_id is required", tool_id="profile.preset")
        action = params.get("action", "list")
        self._mgr.get_or_create_profile(user_id)
        if action == "save":
            preset_name = params.get("preset_name", "")
            if not preset_name:
                return ToolResult.fail("preset_name is required for save", tool_id="profile.preset")
            ok = self._mgr.save_preset(user_id, preset_name, description=params.get("description", ""))
            if not ok:
                return ToolResult.fail(f"Preset '{preset_name}' already exists", tool_id="profile.preset")
            return ToolResult.ok(data={"preset_name": preset_name, "status": "saved"}, tool_id="profile.preset")
        if action == "apply":
            preset_name = params.get("preset_name", "")
            if not preset_name:
                return ToolResult.fail("preset_name is required for apply", tool_id="profile.preset")
            result = self._mgr.apply_preset(user_id, preset_name)
            if "error" in result:
                return ToolResult.fail(result["error"], tool_id="profile.preset")
            return ToolResult.ok(data=result, tool_id="profile.preset")
        if action == "delete":
            preset_name = params.get("preset_name", "")
            if not preset_name:
                return ToolResult.fail("preset_name is required for delete", tool_id="profile.preset")
            self._mgr.delete_preset(user_id, preset_name)
            return ToolResult.ok(data={"preset_name": preset_name, "status": "deleted"}, tool_id="profile.preset")
        presets = self._mgr.list_presets(user_id)
        return ToolResult.ok(data={"presets": presets, "count": len(presets)}, tool_id="profile.preset")


class ProfileHistoryTool(Tool):
    def __init__(self, profile_mgr: UserProfileManager):
        self._mgr = profile_mgr

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="profile.history",
            name="Profile History",
            description="View recent profile and preference changes.",
            version="0.1.0",
            category=_TOOL_CATEGORY,
            parameters={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "User ID (defaults to context user)"},
                    "limit": {"type": "integer", "description": "Max entries (default 20)"},
                },
                "required": [],
            },
            required_permissions=["system.read"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        ctx = context or {}
        identity = ctx.get("identity", {})
        user_id = params.get("user_id") or identity.get("user_id")
        if not user_id:
            return ToolResult.fail("user_id is required", tool_id="profile.history")
        limit = params.get("limit", 20)
        history = self._mgr.get_profile_history(user_id, limit=limit)
        return ToolResult.ok(data={"history": history, "count": len(history)}, tool_id="profile.history")
