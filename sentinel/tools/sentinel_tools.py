from typing import Any, Dict
from sentinel.core.tool import Tool, ToolResult, ToolSpec


class SentinelProcessTool(Tool):
    def __init__(self, get_orchestrator_fn):
        self._get_orch = get_orchestrator_fn

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="sentinel.process",
            name="Sentinel Process",
            description="Process a natural language intent through the Sentinel pipeline",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "utterance": {"type": "string", "description": "Natural language input"},
                },
                "required": ["utterance"],
            },
            required_permissions=["sentinel.process"],
            timeout_seconds=120,
            category="sentinel",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            orch = self._get_orch()
            utterance = params["utterance"]
            identity = context.get("identity", {})
            result = await orch.process(utterance, identity=identity)
            return ToolResult.ok(
                data=result.to_dict() if hasattr(result, "to_dict") else result, tool_id="sentinel.process"
            )
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="sentinel.process")
