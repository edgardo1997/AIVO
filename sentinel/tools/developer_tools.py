from typing import Any, Dict, Optional
from sentinel.core.tool import Tool, ToolResult, ToolSpec

_CAT = "developer"


class DevStatusTool(Tool):
    def __init__(self, svc):
        self._svc = svc
    def spec(self) -> ToolSpec:
        return ToolSpec(id="developer.status", name="Developer Mode Status", description="Current developer mode status", version="1.0.0", category=_CAT, parameters={"type": "object", "properties": {}, "required": []}, required_permissions=["system.read"])
    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        return ToolResult.ok(data=self._svc.status(), tool_id="developer.status")


class DevActivateTool(Tool):
    def __init__(self, svc):
        self._svc = svc
    def spec(self) -> ToolSpec:
        return ToolSpec(id="developer.activate", name="Activate Developer Mode", description="Activate developer mode", version="1.0.0", category=_CAT, parameters={"type": "object", "properties": {}, "required": []}, required_permissions=["system.write"])
    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        sid = (context or {}).get("session_id", "")
        rid = (context or {}).get("request_id", "")
        return ToolResult.ok(data=self._svc.activate(session_id=sid, request_id=rid), tool_id="developer.activate")


class DevDeactivateTool(Tool):
    def __init__(self, svc):
        self._svc = svc
    def spec(self) -> ToolSpec:
        return ToolSpec(id="developer.deactivate", name="Deactivate Developer Mode", description="Deactivate developer mode", version="1.0.0", category=_CAT, parameters={"type": "object", "properties": {}, "required": []}, required_permissions=["system.write"])
    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        sid = (context or {}).get("session_id", "")
        rid = (context or {}).get("request_id", "")
        return ToolResult.ok(data=self._svc.deactivate(session_id=sid, request_id=rid), tool_id="developer.deactivate")


class DevSetProjectTool(Tool):
    def __init__(self, svc):
        self._svc = svc
    def spec(self) -> ToolSpec:
        return ToolSpec(id="developer.project.set", name="Set Dev Project", description="Set the active development project path", version="1.0.0", category=_CAT, parameters={"type": "object", "properties": {"path": {"type": "string", "description": "Project directory path"}}, "required": ["path"]}, required_permissions=["filesystem.write"])
    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        sid = (context or {}).get("session_id", "")
        rid = (context or {}).get("request_id", "")
        return ToolResult.ok(data=self._svc.set_project(params.get("path", ""), session_id=sid, request_id=rid), tool_id="developer.project.set")


class DevSetEnvTool(Tool):
    def __init__(self, svc):
        self._svc = svc
    def spec(self) -> ToolSpec:
        return ToolSpec(id="developer.env.set", name="Set Dev Env Var", description="Set an environment variable for the dev environment", version="1.0.0", category=_CAT, parameters={"type": "object", "properties": {"key": {"type": "string"}, "value": {"type": "string"}}, "required": ["key", "value"]}, required_permissions=["system.write"])
    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        sid = (context or {}).get("session_id", "")
        rid = (context or {}).get("request_id", "")
        return ToolResult.ok(data=self._svc.update_env(params.get("key", ""), params.get("value", ""), session_id=sid, request_id=rid), tool_id="developer.env.set")
