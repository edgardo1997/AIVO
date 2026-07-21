from typing import Any, Dict
from sentinel.core.tool import Tool, ToolResult, ToolSpec


class PermissionConfirmTool(Tool):
    def __init__(self, service):
        self._svc = service

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="permissions.confirm",
            name="Confirm Action",
            description="Approve or deny a pending action by action_id",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "action_id": {"type": "string", "description": "Action ID to confirm"},
                    "approved": {"type": "boolean", "description": "Whether to approve"},
                },
                "required": ["action_id", "approved"],
            },
            required_permissions=["permissions.admin"],
            timeout_seconds=10,
            category="permissions",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            result = self._svc.confirm_action(params["action_id"], params["approved"])
            return ToolResult.ok(data=result, tool_id="permissions.confirm")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="permissions.confirm")


class PermissionStatusTool(Tool):
    def __init__(self, service):
        self._svc = service

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="permissions.status",
            name="Permission Status",
            description="Get current permission level and emergency stop status",
            version="1.0.0",
            parameters={},
            required_permissions=["permissions.read"],
            timeout_seconds=10,
            category="permissions",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            result = self._svc.get_status()
            return ToolResult.ok(data=result, tool_id="permissions.status")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="permissions.status")


class PermissionSetLevelTool(Tool):
    def __init__(self, service):
        self._svc = service

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="permissions.set_level",
            name="Set Permission Level",
            description="Change the permission level (view, confirm, auto, admin)",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "level": {
                        "type": "string",
                        "enum": ["view", "confirm", "auto", "admin"],
                        "description": "Permission level to set",
                    },
                },
                "required": ["level"],
            },
            required_permissions=["permissions.admin"],
            timeout_seconds=10,
            category="permissions",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            result = self._svc.set_level(params["level"])
            return ToolResult.ok(data=result, tool_id="permissions.set_level")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="permissions.set_level")


class PermissionEmergencyTool(Tool):
    def __init__(self, service):
        self._svc = service

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="permissions.emergency",
            name="Emergency Stop",
            description="Activate or deactivate emergency stop",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["stop", "resume"],
                        "description": "stop to halt all execution, resume to restore",
                    },
                },
                "required": ["action"],
            },
            required_permissions=["permissions.admin"],
            timeout_seconds=10,
            category="permissions",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            result = self._svc.emergency(params["action"])
            return ToolResult.ok(data=result, tool_id="permissions.emergency")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="permissions.emergency")


class PermissionAddRuleTool(Tool):
    def __init__(self, service):
        self._svc = service

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="permissions.add_rule",
            name="Add Permission Rule",
            description="Add a granular permission rule",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "tool_pattern": {"type": "string", "description": "Tool ID glob pattern"},
                    "effect": {"type": "string", "enum": ["allow", "deny"], "description": "Allow or deny"},
                    "reason": {"type": "string", "description": "Optional reason"},
                },
                "required": ["tool_pattern", "effect"],
            },
            required_permissions=["permissions.admin"],
            timeout_seconds=10,
            category="permissions",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            result = self._svc.add_rule(params)
            return ToolResult.ok(data={"rule": result}, tool_id="permissions.add_rule")
        except ValueError as e:
            return ToolResult.fail(error=str(e), tool_id="permissions.add_rule")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="permissions.add_rule")


class PermissionRemoveRuleTool(Tool):
    def __init__(self, service):
        self._svc = service

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="permissions.remove_rule",
            name="Remove Permission Rule",
            description="Remove a granular permission rule by ID",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "rule_id": {"type": "string", "description": "Rule ID to remove"},
                },
                "required": ["rule_id"],
            },
            required_permissions=["permissions.admin"],
            timeout_seconds=10,
            category="permissions",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            ok = self._svc.remove_rule(params["rule_id"])
            if not ok:
                return ToolResult.fail(error="Rule not found", tool_id="permissions.remove_rule")
            return ToolResult.ok(data={"deleted": True, "rule_id": params["rule_id"]}, tool_id="permissions.remove_rule")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="permissions.remove_rule")
