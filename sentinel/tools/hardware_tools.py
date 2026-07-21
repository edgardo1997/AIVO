from typing import Any, Dict, Optional

from sentinel.core.tool import Tool, ToolResult, ToolSpec
from sentinel.core import power_manager
from sentinel.core import process_manager
from sentinel.core import gpu_manager

_CAT = "hardware"


class HardwarePowerListTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="hardware.power.list",
            name="List Power Plans",
            description="List all available Windows power plans",
            version="1.0.0",
            category=_CAT,
            parameters={"type": "object", "properties": {}, "required": []},
            required_permissions=["system.read"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        result = power_manager.list_plans()
        if not result.success:
            return ToolResult.fail(error=result.error or "Failed to list power plans", tool_id="hardware.power.list")
        return ToolResult.ok(data={"plans": [{"guid": p.guid, "name": p.name, "active": p.active} for p in result.plans], "active_guid": result.active_guid, "active_name": result.active_name}, tool_id="hardware.power.list")


class HardwarePowerStatusTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="hardware.power.status",
            name="Power Plan Status",
            description="Get the current active Windows power plan",
            version="1.0.0",
            category=_CAT,
            parameters={"type": "object", "properties": {}, "required": []},
            required_permissions=["system.read"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        result = power_manager.get_active_plan()
        if not result.success:
            return ToolResult.fail(error=result.error or "Failed to get active power plan", tool_id="hardware.power.status")
        return ToolResult.ok(data={"active_guid": result.active_guid, "active_name": result.active_name}, tool_id="hardware.power.status")


class HardwarePowerSetTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="hardware.power.set",
            name="Set Power Plan",
            description="Change the active Windows power plan by GUID or alias (balanced, high_performance, power_saver)",
            version="1.0.0",
            category=_CAT,
            parameters={
                "type": "object",
                "properties": {
                    "plan": {
                        "type": "string",
                        "description": "Power plan GUID or alias (balanced, high_performance, power_saver)",
                    },
                },
                "required": ["plan"],
            },
            required_permissions=["system.write"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        plan = params.get("plan", "")
        if not plan:
            return ToolResult.fail(error="plan parameter is required", tool_id="hardware.power.set")
        result = power_manager.set_active_plan(plan)
        if not result.success:
            return ToolResult.fail(error=result.error or f"Failed to set power plan to {plan}", tool_id="hardware.power.set")
        return ToolResult.ok(data={"active_guid": result.active_guid, "active_name": result.active_name, "previous": ""}, tool_id="hardware.power.set")


class ProcessListTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="process.list",
            name="List Processes",
            description="List running Windows processes with optional name filter",
            version="1.0.0",
            category=_CAT,
            parameters={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Optional filter by process name or command line",
                    },
                    "include_system": {
                        "type": "boolean",
                        "description": "Include protected system processes",
                        "default": False,
                    },
                },
                "required": [],
            },
            required_permissions=["system.read"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        result = process_manager.list_processes(
            name_filter=params.get("name"),
            include_system=params.get("include_system", False),
        )
        if not result.success:
            return ToolResult.fail(error=result.error or "Failed to list processes", tool_id="process.list")
        return ToolResult.ok(data={
            "processes": [
                {"pid": p.pid, "name": p.name, "exe": p.exe, "status": p.status,
                 "cpu_percent": p.cpu_percent, "memory_mb": round(p.memory_mb, 1),
                 "username": p.username, "is_system": p.is_system}
                for p in result.processes
            ],
            "count": len(result.processes),
        }, tool_id="process.list")


class ProcessKillTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="process.kill",
            name="Kill Process",
            description="Kill a process by PID or name. Protects system processes.",
            version="1.0.0",
            category=_CAT,
            parameters={
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "PID (number) or process name to kill",
                    },
                    "force": {
                        "type": "boolean",
                        "description": "Force kill if graceful termination fails",
                        "default": True,
                    },
                },
                "required": ["target"],
            },
            required_permissions=["system.write"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        target = params.get("target", "")
        if not target:
            return ToolResult.fail(error="target parameter is required", tool_id="process.kill")
        result = process_manager.kill_process(target, force=params.get("force", True))
        if not result.success:
            return ToolResult.fail(error=result.error or f"Failed to kill '{target}'", tool_id="process.kill")
        return ToolResult.ok(data={"message": result.message, "errors": result.error}, tool_id="process.kill")


class ProcessSuspendTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="process.suspend",
            name="Suspend Process",
            description="Suspend a process by PID or name using NtSuspendProcess. Protects system processes.",
            version="1.0.0",
            category=_CAT,
            parameters={
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "PID (number) or process name to suspend",
                    },
                },
                "required": ["target"],
            },
            required_permissions=["system.write"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        target = params.get("target", "")
        if not target:
            return ToolResult.fail(error="target parameter is required", tool_id="process.suspend")
        result = process_manager.suspend_process(target)
        if not result.success:
            return ToolResult.fail(error=result.error or f"Failed to suspend '{target}'", tool_id="process.suspend")
        return ToolResult.ok(data={"message": result.message, "errors": result.error}, tool_id="process.suspend")


class ProcessResumeTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="process.resume",
            name="Resume Process",
            description="Resume a suspended process by PID or name using NtResumeProcess.",
            version="1.0.0",
            category=_CAT,
            parameters={
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "PID (number) or process name to resume",
                    },
                },
                "required": ["target"],
            },
            required_permissions=["system.write"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        target = params.get("target", "")
        if not target:
            return ToolResult.fail(error="target parameter is required", tool_id="process.resume")
        result = process_manager.resume_process(target)
        if not result.success:
            return ToolResult.fail(error=result.error or f"Failed to resume '{target}'", tool_id="process.resume")
        return ToolResult.ok(data={"message": result.message, "errors": result.error}, tool_id="process.resume")


class ProcessPriorityTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="process.priority",
            name="Set Process Priority",
            description="Change a process's priority class by PID or name. Values: idle, below_normal, normal, above_normal, high, realtime",
            version="1.0.0",
            category=_CAT,
            parameters={
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "PID (number) or process name",
                    },
                    "priority": {
                        "type": "string",
                        "description": "Priority class: idle, below_normal, normal, above_normal, high, realtime",
                        "enum": ["idle", "below_normal", "normal", "above_normal", "high", "realtime"],
                    },
                },
                "required": ["target", "priority"],
            },
            required_permissions=["system.write"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        target = params.get("target", "")
        priority = params.get("priority", "")
        if not target:
            return ToolResult.fail(error="target parameter is required", tool_id="process.priority")
        if not priority:
            return ToolResult.fail(error="priority parameter is required", tool_id="process.priority")
        result = process_manager.set_priority(target, priority)
        if not result.success:
            return ToolResult.fail(error=result.error or f"Failed to set priority for '{target}'", tool_id="process.priority")
        return ToolResult.ok(data={"message": result.message, "errors": result.error}, tool_id="process.priority")


class GpuListTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="gpu.list",
            name="List GPUs",
            description="List all available NVIDIA GPUs with detailed info",
            version="1.0.0",
            category=_CAT,
            parameters={"type": "object", "properties": {}, "required": []},
            required_permissions=["system.read"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        result = gpu_manager.list_gpus()
        if not result.success:
            return ToolResult.ok(data={"gpus": [], "message": result.error or "No GPU information available"}, tool_id="gpu.list")
        return ToolResult.ok(data={"gpus": [g.__dict__ for g in result.gpus]}, tool_id="gpu.list")


class GpuStatusTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="gpu.status",
            name="GPU Status",
            description="Get real-time status for a specific GPU",
            version="1.0.0",
            category=_CAT,
            parameters={
                "type": "object",
                "properties": {
                    "index": {"type": "integer", "description": "GPU index", "default": 0},
                },
                "required": [],
            },
            required_permissions=["system.read"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        idx = params.get("index", 0)
        result = gpu_manager.get_gpu_status(idx)
        if not result.success:
            return ToolResult.fail(error=result.error or f"GPU {idx} not found", tool_id="gpu.status")
        return ToolResult.ok(data={"gpu": result.gpus[0].__dict__}, tool_id="gpu.status")


class GpuProfileTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="gpu.profile",
            name="GPU Profile",
            description="Apply a GPU tuning profile: default, gaming, max_performance, quiet, power_saver",
            version="1.0.0",
            category=_CAT,
            parameters={
                "type": "object",
                "properties": {
                    "profile": {
                        "type": "string",
                        "description": "GPU profile name",
                        "enum": ["default", "gaming", "max_performance", "quiet", "power_saver"],
                    },
                    "index": {"type": "integer", "description": "GPU index", "default": 0},
                },
                "required": ["profile"],
            },
            required_permissions=["system.write"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        profile = params.get("profile", "")
        if not profile:
            return ToolResult.fail(error="profile parameter is required", tool_id="gpu.profile")
        idx = params.get("index", 0)
        result = gpu_manager.set_gpu_profile(profile, idx)
        if not result.success:
            return ToolResult.fail(error=result.error or f"Failed to apply GPU profile '{profile}'", tool_id="gpu.profile")
        return ToolResult.ok(data={"message": result.message, "errors": result.error}, tool_id="gpu.profile")


class GpuPowerLimitTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="gpu.power_limit",
            name="GPU Power Limit",
            description="Set GPU power limit in watts",
            version="1.0.0",
            category=_CAT,
            parameters={
                "type": "object",
                "properties": {
                    "watts": {"type": "integer", "description": "Power limit in watts"},
                    "index": {"type": "integer", "description": "GPU index", "default": 0},
                },
                "required": ["watts"],
            },
            required_permissions=["system.write"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        watts = params.get("watts")
        if watts is None:
            return ToolResult.fail(error="watts parameter is required", tool_id="gpu.power_limit")
        idx = params.get("index", 0)
        result = gpu_manager.set_power_limit(watts, idx)
        if not result.success:
            return ToolResult.fail(error=result.error or f"Failed to set power limit to {watts}W", tool_id="gpu.power_limit")
        return ToolResult.ok(data={"message": result.message}, tool_id="gpu.power_limit")


class GpuResetTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="gpu.reset",
            name="Reset GPU",
            description="Reset GPU clocks, power limit, and fan to defaults",
            version="1.0.0",
            category=_CAT,
            parameters={
                "type": "object",
                "properties": {
                    "index": {"type": "integer", "description": "GPU index", "default": 0},
                },
                "required": [],
            },
            required_permissions=["system.write"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        idx = params.get("index", 0)
        result = gpu_manager.reset_gpu(idx)
        if not result.success:
            return ToolResult.fail(error=result.error or f"Failed to reset GPU {idx}", tool_id="gpu.reset")
        return ToolResult.ok(data={"message": result.message, "errors": result.error}, tool_id="gpu.reset")
