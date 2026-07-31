import logging
from typing import Any, Dict, List, Optional
from sentinel.routing.capability_selector import CapabilitySelector
from sentinel.core.tool_schema_adapter import to_openai_tools, parse_tool_call, build_assistant_tool_message, build_tool_result_message, build_tool_error_message

logger = logging.getLogger(__name__)


class ToolExecutor:
    def __init__(self, capability_selector: Optional[CapabilitySelector] = None):
        self._tool_gateway: Any = None
        self._tool_guard: Any = None
        self._capability_selector = capability_selector or CapabilitySelector()

    def set_tool_gateway(self, gateway: Any) -> None:
        self._tool_gateway = gateway

    def set_tool_guard(self, guard: Any) -> None:
        self._tool_guard = guard

    def set_capability_selector(self, selector: CapabilitySelector) -> None:
        self._capability_selector = selector

    async def execute_tool_call(self, tool_call: Dict[str, Any], provider_id: str, model_id: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from sentinel.security.models import ToolRequest

        tool_name = tool_call["function"]["name"]
        arguments = tool_call["function"]["arguments"]
        tool_call_id = tool_call["id"]

        if self._tool_guard is None:
            logger.error(
                "ToolExecutionGuard not configured — rejecting tool '%s' execution",
                tool_name,
            )
            return build_tool_error_message(
                tool_call_id, tool_name,
                "ToolExecutionGuard not configured — execution rejected",
            )

        user_context = dict(context or {})
        user_context["source"] = "model_router"
        user_context["provider_id"] = provider_id
        user_context["model_id"] = model_id

        request = ToolRequest(
            tool_name=tool_name,
            arguments=arguments,
            source=f"model:{model_id}/provider:{provider_id}",
            user_context=user_context,
            session_id=user_context.get("session_id", ""),
            user_id=user_context.get("user_id", ""),
            execution_id=user_context.get("execution_id", ""),
            model_id=model_id,
            provider_id=provider_id,
        )

        guard_result = await self._tool_guard.execute(request)
        if guard_result.success:
            return build_tool_result_message(tool_call_id, tool_name, guard_result.data)
        return build_tool_error_message(tool_call_id, tool_name, guard_result.error or "Blocked by ToolExecutionGuard")

    async def handle_tool_calls(self, tool_calls: List[Dict[str, Any]], provider_id: str, model_id: str, context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        if not self._capability_selector.validate_tool_call_compatibility(model_id, provider_id):
            raise RuntimeError(
                f"Tool calling rejected: model '{model_id}' (provider={provider_id}) "
                f"does not support tool calling"
            )
        tool_result_messages = []
        for tc in tool_calls:
            tool_name = tc["function"]["name"]
            logger.info("Tool call: model=%s tool=%s args=%s", model_id, tool_name, tc["function"]["arguments"])
            msg = await self.execute_tool_call(tc, provider_id, model_id, context=context)
            tool_result_messages.append(msg)
        return tool_result_messages
