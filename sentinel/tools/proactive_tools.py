from typing import Any, Dict
from sentinel.core.tool import Tool, ToolResult, ToolSpec


class ProactiveSuggestionsTool(Tool):
    def __init__(self, service):
        self._svc = service

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="proactive.suggestions",
            name="Get Proactive Suggestions",
            description="List current proactive suggestions, trends, and engine status",
            version="0.1.0",
            parameters={},
            required_permissions=["proactive.read"],
            timeout_seconds=10,
            category="proactive",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            result = self._svc.get_suggestions()
            return ToolResult.ok(data=result, tool_id="proactive.suggestions")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="proactive.suggestions")


class ProactiveDismissTool(Tool):
    def __init__(self, service):
        self._svc = service

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="proactive.dismiss",
            name="Dismiss Suggestion",
            description="Dismiss a proactive suggestion by id or uid",
            version="0.1.0",
            parameters={
                "type": "object",
                "properties": {
                    "suggestion_id": {"type": "string", "description": "Suggestion id or uid to dismiss"},
                },
                "required": ["suggestion_id"],
            },
            required_permissions=["proactive.write"],
            timeout_seconds=10,
            category="proactive",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            result = self._svc.dismiss_suggestion(params["suggestion_id"])
            return ToolResult.ok(data=result, tool_id="proactive.dismiss")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="proactive.dismiss")


class ProactiveTrendTool(Tool):
    def __init__(self, service):
        self._svc = service

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="proactive.trend",
            name="Get Metrics Trend",
            description="Get CPU, memory, and disk usage trends over time",
            version="0.1.0",
            parameters={},
            required_permissions=["proactive.read"],
            timeout_seconds=10,
            category="proactive",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            result = self._svc.get_trend()
            return ToolResult.ok(data=result, tool_id="proactive.trend")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="proactive.trend")
