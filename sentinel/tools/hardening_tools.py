import logging
from typing import Any, Dict, Optional

from sentinel.core.hardening import HardeningService
from sentinel.core.tool import Tool, ToolResult, ToolSpec

logger = logging.getLogger(__name__)

_TOOL_CATEGORY = "hardening"


class HardeningStatusTool(Tool):
    def __init__(self, hardening: HardeningService):
        self._hardening = hardening

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="hardening.status",
            name="Hardening Status",
            description="View hardening configuration, circuit breaker states, and retry/timeout stats.",
            version="1.0.0",
            category=_TOOL_CATEGORY,
            parameters={},
            required_permissions=["system.read"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        data = self._hardening.stats()
        return ToolResult.ok(data=data, tool_id="hardening.status")


class HardeningResetTool(Tool):
    def __init__(self, hardening: HardeningService):
        self._hardening = hardening

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="hardening.reset",
            name="Reset Hardening State",
            description="Reset circuit breakers and retry stats for a specific tool or all tools.",
            version="1.0.0",
            category=_TOOL_CATEGORY,
            parameters={
                "type": "object",
                "properties": {
                    "tool_id": {"type": "string", "description": "Optional tool ID to reset (empty = reset all)"},
                },
                "required": [],
            },
            required_permissions=["permissions.admin"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        tool_id = params.get("tool_id", "")
        reset_id = tool_id if tool_id else None
        count = self._hardening.circuit_breaker.reset(reset_id)
        return ToolResult.ok(
            data={"reset": tool_id or "all", "circuits_reset": count},
            tool_id="hardening.reset",
        )


class HardeningConfigTool(Tool):
    def __init__(self, hardening: HardeningService):
        self._hardening = hardening

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="hardening.config",
            name="Hardening Configuration",
            description="View or update hardening configuration. To update, pass the params to change.",
            version="1.0.0",
            category=_TOOL_CATEGORY,
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["get", "set", "tool_override", "remove_override"],
                        "description": "Action to perform",
                    },
                    "tool_id": {"type": "string", "description": "Tool ID for tool-specific overrides"},
                    "timeout_seconds": {"type": "integer", "description": "Default timeout in seconds"},
                    "circuit_breaker_threshold": {"type": "integer", "description": "Failures before circuit opens"},
                    "circuit_breaker_cooldown": {"type": "number", "description": "Cooldown seconds before half-open"},
                    "retry_jitter": {"type": "number", "description": "Jitter fraction for retry backoff"},
                },
                "required": ["action"],
            },
            required_permissions=["permissions.admin"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        action = params.get("action", "get")
        if action == "get":
            return ToolResult.ok(data=self._hardening.stats(), tool_id="hardening.config")
        if action == "set":
            settable = {}
            for key in ("timeout_seconds", "circuit_breaker_threshold", "circuit_breaker_cooldown", "retry_jitter"):
                if key in params:
                    settable[key] = params[key]
            if settable:
                self._hardening.update_config(**settable)
            return ToolResult.ok(data={"updated": settable}, tool_id="hardening.config")
        if action == "tool_override":
            tool_id = params.get("tool_id", "")
            if not tool_id:
                return ToolResult.fail("tool_id is required for tool_override", tool_id="hardening.config")
            overrides = {}
            for key in ("timeout_seconds", "circuit_breaker_threshold", "circuit_breaker_cooldown", "retry_jitter"):
                if key in params:
                    overrides[key] = params[key]
            self._hardening.set_tool_override(tool_id, **overrides)
            return ToolResult.ok(data={"tool_id": tool_id, "overrides": overrides}, tool_id="hardening.config")
        if action == "remove_override":
            tool_id = params.get("tool_id", "")
            if not tool_id:
                return ToolResult.fail("tool_id is required for remove_override", tool_id="hardening.config")
            removed = self._hardening.remove_tool_override(tool_id)
            return ToolResult.ok(data={"tool_id": tool_id, "removed": removed}, tool_id="hardening.config")
        return ToolResult.fail(f"Unknown action: {action}", tool_id="hardening.config")
