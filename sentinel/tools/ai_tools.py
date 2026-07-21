from typing import Any, Dict
from sentinel.core.tool import Tool, ToolResult, ToolSpec


class AIChatTool(Tool):
    def __init__(self, service):
        self._svc = service

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="ai.chat",
            name="AI Chat",
            description="Send a message to the AI assistant and get a response",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "User message"},
                    "system_prompt": {"type": "string", "description": "Optional system prompt override"},
                    "context": {"type": "array", "description": "Previous conversation context"},
                },
                "required": ["message"],
            },
            required_permissions=["ai.chat"],
            timeout_seconds=60,
            category="ai",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            result = self._svc.chat(
                params["message"],
                params.get("system_prompt"),
                params.get("context"),
            )
            return ToolResult.ok(data=result, tool_id="ai.chat")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="ai.chat")


class AIAnalyzeTool(Tool):
    def __init__(self, service):
        self._svc = service

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="ai.analyze",
            name="AI Analyze Metrics",
            description="Analyze system metrics and provide insights",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "metrics": {
                        "type": "object",
                        "description": "System metrics (cpu, memory, disk)",
                    },
                },
                "required": ["metrics"],
            },
            required_permissions=["ai.chat"],
            timeout_seconds=60,
            category="ai",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            result = self._svc.analyze_metrics(params["metrics"])
            return ToolResult.ok(data=result, tool_id="ai.analyze")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="ai.analyze")


class AIConfigTool(Tool):
    def __init__(self, service):
        self._svc = service

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="ai.config",
            name="AI Configuration",
            description="Get or set AI provider configuration",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "provider": {"type": "string", "description": "Provider name"},
                    "api_key": {"type": "string", "description": "API key"},
                    "base_url": {"type": "string", "description": "Base URL override"},
                    "model": {"type": "string", "description": "Model name"},
                    "strategy": {"type": "string", "description": "Model routing strategy"},
                },
            },
            required_permissions=["ai.config"],
            timeout_seconds=10,
            category="ai",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            if params:
                result = self._svc.set_config(params)
            else:
                result = self._svc.get_config()
            return ToolResult.ok(data=result, tool_id="ai.config")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="ai.config")
