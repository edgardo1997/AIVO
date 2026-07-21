from typing import Any, Dict, Optional
from sentinel.core.tool import Tool, ToolResult, ToolSpec

_CAT = "workspace"


class WorkspaceListTool(Tool):
    def __init__(self, svc):
        self._svc = svc
    def spec(self) -> ToolSpec:
        return ToolSpec(id="workspace.list", name="List Workspaces", description="List all workspaces", version="1.0.0", category=_CAT, parameters={"type": "object", "properties": {}, "required": []}, required_permissions=["system.read"])
    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        return ToolResult.ok(data={"workspaces": self._svc.list_workspaces(), "active": self._svc.status()["active"]}, tool_id="workspace.list")


class WorkspaceCreateTool(Tool):
    def __init__(self, svc):
        self._svc = svc
    def spec(self) -> ToolSpec:
        return ToolSpec(id="workspace.create", name="Create Workspace", description="Create a new workspace", version="1.0.0", category=_CAT, parameters={"type": "object", "properties": {"workspace_id": {"type": "string", "description": "Unique workspace ID"}, "path": {"type": "string", "description": "Optional workspace path"}}, "required": ["workspace_id"]}, required_permissions=["filesystem.write"])
    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        sid = (context or {}).get("session_id", "")
        rid = (context or {}).get("request_id", "")
        return ToolResult.ok(data=self._svc.create(params["workspace_id"], path=params.get("path", ""), session_id=sid, request_id=rid), tool_id="workspace.create")


class WorkspaceOpenTool(Tool):
    def __init__(self, svc):
        self._svc = svc
    def spec(self) -> ToolSpec:
        return ToolSpec(id="workspace.open", name="Open Workspace", description="Open an existing workspace", version="1.0.0", category=_CAT, parameters={"type": "object", "properties": {"workspace_id": {"type": "string"}}, "required": ["workspace_id"]}, required_permissions=["system.read"])
    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        sid = (context or {}).get("session_id", "")
        rid = (context or {}).get("request_id", "")
        return ToolResult.ok(data=self._svc.open(params["workspace_id"], session_id=sid, request_id=rid), tool_id="workspace.open")


class WorkspaceCloseTool(Tool):
    def __init__(self, svc):
        self._svc = svc
    def spec(self) -> ToolSpec:
        return ToolSpec(id="workspace.close", name="Close Workspace", description="Close the active workspace", version="1.0.0", category=_CAT, parameters={"type": "object", "properties": {}, "required": []}, required_permissions=["system.read"])
    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        sid = (context or {}).get("session_id", "")
        rid = (context or {}).get("request_id", "")
        return ToolResult.ok(data=self._svc.close(session_id=sid, request_id=rid), tool_id="workspace.close")


class WorkspaceDeleteTool(Tool):
    def __init__(self, svc):
        self._svc = svc
    def spec(self) -> ToolSpec:
        return ToolSpec(id="workspace.delete", name="Delete Workspace", description="Delete a workspace", version="1.0.0", category=_CAT, parameters={"type": "object", "properties": {"workspace_id": {"type": "string"}}, "required": ["workspace_id"]}, required_permissions=["filesystem.write"])
    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        sid = (context or {}).get("session_id", "")
        rid = (context or {}).get("request_id", "")
        return ToolResult.ok(data=self._svc.delete(params["workspace_id"], session_id=sid, request_id=rid), tool_id="workspace.delete")
