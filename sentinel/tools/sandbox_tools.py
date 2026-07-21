from typing import Any, Dict, Optional

from sentinel.core.tool import Tool, ToolResult, ToolSpec
from sentinel.core.sandbox import (
    SandboxLimits, create_sandbox, assign_process,
    terminate_sandbox, close_sandbox, get_sandbox_info,
    list_sandboxes, cleanup_all,
)

_CAT = "sandbox"


class SandboxCreateTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="sandbox.create",
            name="Create Sandbox",
            description="Create a Windows JobObject sandbox with optional resource limits",
            version="1.0.0",
            category=_CAT,
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Optional sandbox name"},
                    "max_processes": {"type": "integer", "description": "Max process count (0 = unlimited)", "default": 0},
                    "memory_limit_mb": {"type": "integer", "description": "Memory limit in MB (0 = unlimited)", "default": 0},
                    "cpu_percent": {"type": "integer", "description": "CPU rate limit %% (0 = unlimited)", "default": 0},
                },
                "required": [],
            },
            required_permissions=["system.write"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        limits = SandboxLimits(
            max_processes=params.get("max_processes", 0),
            memory_limit_mb=params.get("memory_limit_mb", 0),
            cpu_percent=params.get("cpu_percent", 0),
            kill_on_close=True,
        )
        sb_id = create_sandbox(name=params.get("name"), limits=limits)
        if not sb_id:
            return ToolResult.fail(error="Failed to create sandbox", tool_id="sandbox.create")
        return ToolResult.ok(data={"sandbox_id": sb_id, "limits": limits.__dict__}, tool_id="sandbox.create")


class SandboxAssignTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="sandbox.assign",
            name="Assign Process to Sandbox",
            description="Assign a running process (by PID) to an existing sandbox",
            version="1.0.0",
            category=_CAT,
            parameters={
                "type": "object",
                "properties": {
                    "sandbox_id": {"type": "string", "description": "Sandbox ID"},
                    "pid": {"type": "integer", "description": "Process PID to assign"},
                },
                "required": ["sandbox_id", "pid"],
            },
            required_permissions=["system.write"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        sb_id = params.get("sandbox_id", "")
        pid = params.get("pid", 0)
        if not sb_id:
            return ToolResult.fail(error="sandbox_id parameter is required", tool_id="sandbox.assign")
        if not pid:
            return ToolResult.fail(error="pid parameter is required", tool_id="sandbox.assign")
        ok = assign_process(sb_id, pid)
        if not ok:
            return ToolResult.fail(error=f"Failed to assign PID {pid} to sandbox {sb_id}", tool_id="sandbox.assign")
        return ToolResult.ok(data={"sandbox_id": sb_id, "pid": pid}, tool_id="sandbox.assign")


class SandboxTerminateTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="sandbox.terminate",
            name="Terminate Sandbox",
            description="Kill all processes in a sandbox without removing the sandbox",
            version="1.0.0",
            category=_CAT,
            parameters={
                "type": "object",
                "properties": {
                    "sandbox_id": {"type": "string", "description": "Sandbox ID"},
                },
                "required": ["sandbox_id"],
            },
            required_permissions=["system.write"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        sb_id = params.get("sandbox_id", "")
        if not sb_id:
            return ToolResult.fail(error="sandbox_id parameter is required", tool_id="sandbox.terminate")
        ok = terminate_sandbox(sb_id)
        if not ok:
            return ToolResult.fail(error=f"Failed to terminate sandbox {sb_id}", tool_id="sandbox.terminate")
        return ToolResult.ok(data={"sandbox_id": sb_id, "message": "All processes terminated"}, tool_id="sandbox.terminate")


class SandboxCloseTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="sandbox.close",
            name="Close Sandbox",
            description="Terminate all processes and close a sandbox, removing it",
            version="1.0.0",
            category=_CAT,
            parameters={
                "type": "object",
                "properties": {
                    "sandbox_id": {"type": "string", "description": "Sandbox ID"},
                },
                "required": ["sandbox_id"],
            },
            required_permissions=["system.write"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        sb_id = params.get("sandbox_id", "")
        if not sb_id:
            return ToolResult.fail(error="sandbox_id parameter is required", tool_id="sandbox.close")
        ok = close_sandbox(sb_id)
        if not ok:
            return ToolResult.fail(error=f"Failed to close sandbox {sb_id}", tool_id="sandbox.close")
        return ToolResult.ok(data={"sandbox_id": sb_id, "message": "Sandbox closed"}, tool_id="sandbox.close")


class SandboxInfoTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="sandbox.info",
            name="Sandbox Info",
            description="Get information about a sandbox",
            version="1.0.0",
            category=_CAT,
            parameters={
                "type": "object",
                "properties": {
                    "sandbox_id": {"type": "string", "description": "Sandbox ID"},
                },
                "required": ["sandbox_id"],
            },
            required_permissions=["system.read"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        sb_id = params.get("sandbox_id", "")
        if not sb_id:
            return ToolResult.fail(error="sandbox_id parameter is required", tool_id="sandbox.info")
        info = get_sandbox_info(sb_id)
        if not info:
            return ToolResult.fail(error=f"Sandbox '{sb_id}' not found", tool_id="sandbox.info")
        return ToolResult.ok(data={
            "id": info.id,
            "name": info.name,
            "created_at": info.created_at,
            "process_count": info.process_count,
            "limits": info.limits.__dict__,
            "is_active": info.is_active,
        }, tool_id="sandbox.info")


class SandboxListTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="sandbox.list",
            name="List Sandboxes",
            description="List all active sandboxes",
            version="1.0.0",
            category=_CAT,
            parameters={"type": "object", "properties": {}, "required": []},
            required_permissions=["system.read"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        boxes = list_sandboxes()
        return ToolResult.ok(data={
            "sandboxes": [
                {"id": b.id, "name": b.name, "created_at": b.created_at,
                 "process_count": b.process_count, "limits": b.limits.__dict__}
                for b in boxes
            ],
            "count": len(boxes),
        }, tool_id="sandbox.list")
