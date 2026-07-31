import json
import logging
from typing import Any, Dict, List, Optional

from sentinel.core import ToolSpec

logger = logging.getLogger(__name__)


def to_openai_tool(tool_spec: ToolSpec) -> Dict[str, Any]:
    if tool_spec.status.value != "active":
        logger.debug("Skipping disabled tool '%s' in schema conversion", tool_spec.id)
        return None
    schema = {
        "type": "function",
        "function": {
            "name": tool_spec.id,
            "description": tool_spec.description,
            "parameters": tool_spec.parameters or {"type": "object", "properties": {}},
        },
    }
    if not schema["function"]["parameters"].get("type"):
        schema["function"]["parameters"]["type"] = "object"
    if "properties" not in schema["function"]["parameters"]:
        schema["function"]["parameters"]["properties"] = {}
    return schema


def to_openai_tools(tool_specs: List[ToolSpec]) -> List[Dict[str, Any]]:
    return [t for t in (to_openai_tool(s) for s in tool_specs) if t is not None]


def parse_tool_call(response_message: Any) -> List[Dict[str, Any]]:
    if not hasattr(response_message, "tool_calls") or not response_message.tool_calls:
        return []
    parsed = []
    for tc in response_message.tool_calls:
        raw_args = tc.function.arguments or "{}"
        try:
            arguments = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
        except json.JSONDecodeError:
            logger.warning("Failed to parse tool call arguments for '%s': %s", tc.function.name, raw_args)
            arguments = {}
        parsed.append({
            "id": tc.id,
            "type": "function",
            "function": {
                "name": tc.function.name,
                "arguments": arguments,
            },
        })
    return parsed


def build_assistant_tool_message(tool_calls: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": tc["id"],
                "type": "function",
                "function": {
                    "name": tc["function"]["name"],
                    "arguments": json.dumps(tc["function"]["arguments"]),
                },
            }
            for tc in tool_calls
        ],
    }


def build_tool_result_message(tool_call_id: str, tool_name: str, result: Any) -> Dict[str, Any]:
    content = json.dumps({"success": True, "data": result}) if not isinstance(result, str) else result
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "name": tool_name,
        "content": content,
    }


def build_tool_error_message(tool_call_id: str, tool_name: str, error: str) -> Dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "name": tool_name,
        "content": json.dumps({"success": False, "error": error}),
    }
