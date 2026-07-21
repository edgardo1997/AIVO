from typing import Any, Dict
from sentinel.core.tool import Tool, ToolResult, ToolSpec


class AuditListTool(Tool):
    def __init__(self, service):
        self._svc = service

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="audit.list",
            name="List Audit Log",
            description="Retrieve audit log entries with optional limit and action filter",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max entries to return"},
                    "action_filter": {"type": "string", "description": "Filter by action prefix"},
                },
            },
            required_permissions=["audit.read"],
            timeout_seconds=10,
            category="audit",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            result = self._svc.get_log(limit=params.get("limit"), action_filter=params.get("action_filter"))
            return ToolResult.ok(data=result, tool_id="audit.list")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="audit.list")
