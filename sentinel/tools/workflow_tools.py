from typing import Any, Dict, Optional
from sentinel.core.tool import Tool, ToolResult, ToolSpec

_CAT = "workflow"


class WorkflowListTool(Tool):
    def __init__(self, svc):
        self._svc = svc
    def spec(self) -> ToolSpec:
        return ToolSpec(id="workflow.list", name="List Workflows", description="List all AI workflows", version="1.0.0", category=_CAT, parameters={"type": "object", "properties": {}, "required": []}, required_permissions=["system.read"])
    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        return ToolResult.ok(data={"workflows": self._svc.list_workflows()}, tool_id="workflow.list")


class WorkflowCreateTool(Tool):
    def __init__(self, svc):
        self._svc = svc
    def spec(self) -> ToolSpec:
        return ToolSpec(id="workflow.create", name="Create Workflow", description="Create a new AI workflow with ordered steps", version="1.0.0", category=_CAT, parameters={"type": "object", "properties": {"name": {"type": "string"}, "steps": {"type": "array", "items": {"type": "string"}, "description": "Ordered list of step names"}}, "required": ["name", "steps"]}, required_permissions=["system.write"])
    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        sid = (context or {}).get("session_id", "")
        rid = (context or {}).get("request_id", "")
        return ToolResult.ok(data=self._svc.create(params["name"], params.get("steps", []), session_id=sid, request_id=rid), tool_id="workflow.create")


class WorkflowExecuteTool(Tool):
    def __init__(self, svc):
        self._svc = svc
    def spec(self) -> ToolSpec:
        return ToolSpec(id="workflow.execute", name="Execute Workflow", description="Start or advance a workflow execution", version="1.0.0", category=_CAT, parameters={"type": "object", "properties": {"workflow_id": {"type": "string"}, "action": {"type": "string", "enum": ["start", "step", "complete", "fail"], "description": "Action: start, step, complete, or fail"}, "step_result": {"type": "string", "description": "Result data for a step execution"}, "error": {"type": "string", "description": "Error message for fail action"}}, "required": ["workflow_id", "action"]}, required_permissions=["system.write"])
    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        sid = (context or {}).get("session_id", "")
        rid = (context or {}).get("request_id", "")
        wid = params["workflow_id"]
        action = params["action"]
        if action == "start":
            data = self._svc.start(wid, session_id=sid, request_id=rid)
        elif action == "step":
            data = self._svc.execute_step(wid, step_result=params.get("step_result", ""), session_id=sid, request_id=rid)
        elif action == "complete":
            data = self._svc.complete(wid, session_id=sid, request_id=rid)
        elif action == "fail":
            data = self._svc.fail(wid, error=params.get("error", ""), session_id=sid, request_id=rid)
        else:
            return ToolResult.error(f"Unknown action: {action}", tool_id="workflow.execute")
        return ToolResult.ok(data=data, tool_id="workflow.execute")


class WorkflowCancelTool(Tool):
    def __init__(self, svc):
        self._svc = svc
    def spec(self) -> ToolSpec:
        return ToolSpec(id="workflow.cancel", name="Cancel Workflow", description="Cancel a running workflow", version="1.0.0", category=_CAT, parameters={"type": "object", "properties": {"workflow_id": {"type": "string"}}, "required": ["workflow_id"]}, required_permissions=["system.write"])
    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        sid = (context or {}).get("session_id", "")
        rid = (context or {}).get("request_id", "")
        return ToolResult.ok(data=self._svc.fail(params["workflow_id"], error="cancelled", session_id=sid, request_id=rid), tool_id="workflow.cancel")
