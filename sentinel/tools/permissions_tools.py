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
            version="0.1.0",
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
            version="0.1.0",
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
            version="0.1.0",
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
            version="0.1.0",
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
