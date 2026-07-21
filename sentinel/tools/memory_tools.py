import logging
from typing import Any, Dict, Optional

from sentinel.core.tool import Tool, ToolResult, ToolSpec

logger = logging.getLogger(__name__)


def _get_memory():
    from modules import get_sentinel_memory
    memory = get_sentinel_memory()
    if memory is None:
        from modules import get_sentinel_orchestrator
        orch = get_sentinel_orchestrator()
        memory = getattr(orch, "_memory", None)
    return memory


def _audit(action, detail, status, user=""):
    try:
        from modules.audit import _svc as audit_service
        audit_service.log_action(action, detail, status, user=user)
    except Exception:
        pass


class MemorySessionDeleteTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="memory.session.delete",
            name="Delete Memory Session",
            description="Delete a memory session and its records.",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "user_id": {"type": "string"},
                },
                "required": ["session_id", "user_id"],
            },
            required_permissions=["system.read"],
            category="memory",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        memory = _get_memory()
        if memory is None:
            return ToolResult.fail(error="Memory not available", tool_id="memory.session.delete")
        deleted = memory.delete_session(params["session_id"], params["user_id"])
        if not deleted:
            return ToolResult.fail(error="Session not found", tool_id="memory.session.delete")
        _audit("memory_session_delete", params["session_id"], "success", user=params["user_id"])
        return ToolResult.ok(data={"deleted": True, "session_id": params["session_id"], "records_deleted": deleted}, tool_id="memory.session.delete")


class EnvironmentMemoryDeleteTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="memory.environment.delete",
            name="Delete Environment Memory",
            description="Delete privacy-sensitive environmental observations.",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                },
                "required": ["user_id"],
            },
            required_permissions=["system.read"],
            category="memory",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        memory = _get_memory()
        if memory is None:
            return ToolResult.fail(error="Memory not available", tool_id="memory.environment.delete")
        deleted = memory.delete_environment_data(params["user_id"])
        _audit("environment_memory_delete", f"records={deleted}", "success", user=params["user_id"])
        return ToolResult.ok(data={"deleted": True, "records_deleted": deleted}, tool_id="memory.environment.delete")
