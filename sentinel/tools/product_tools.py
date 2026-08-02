"""Governed tools for Product Experience system actions."""

from typing import Any, Dict, Optional

from sentinel.core.tool import Tool, ToolResult, ToolSpec


class _ProductTool(Tool):
    def __init__(self, modes, control) -> None:
        self._modes = modes
        self._control = control


class ProductModeActivateTool(_ProductTool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="product.mode.activate", name="Activate Product Mode",
            description="Activate a product mode and apply its governed platform changes.",
            version="1.0.0", category="product",
            parameters={"type": "object", "properties": {
                "mode_id": {"type": "string"}, "reason": {"type": "string"},
                "platform_apply": {"type": "boolean", "default": True},
            }, "required": ["mode_id"]},
            required_permissions=["system.write"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        result = self._modes.activate(
            params["mode_id"], reason=params.get("reason", ""),
            _platform_apply=params.get("platform_apply", True),
        )
        if not result.get("success"):
            return ToolResult.fail(result.get("error", "Mode activation failed"), tool_id="product.mode.activate")
        return ToolResult.ok(data=result, tool_id="product.mode.activate")


class ProductModeDeactivateTool(_ProductTool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="product.mode.deactivate", name="Deactivate Product Mode",
            description="Deactivate the active product mode and apply its governed rollback.",
            version="1.0.0", category="product",
            parameters={"type": "object", "properties": {"reason": {"type": "string"}}},
            required_permissions=["system.write"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        return ToolResult.ok(
            data=self._modes.deactivate(reason=params.get("reason", "")),
            tool_id="product.mode.deactivate",
        )


class ProductModeRollbackTool(_ProductTool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="product.mode.rollback", name="Rollback Product Mode",
            description="Restore the previous product mode snapshot.", version="1.0.0", category="product",
            parameters={"type": "object", "properties": {}}, required_permissions=["system.write"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        result = self._modes.rollback()
        if not result.get("success"):
            return ToolResult.fail(result.get("error", "Mode rollback failed"), tool_id="product.mode.rollback")
        return ToolResult.ok(data=result, tool_id="product.mode.rollback")


class ProductOptimizeTool(_ProductTool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="product.control.optimize", name="Optimize System",
            description="Run the product control-center optimizer through the governed boundary.",
            version="1.0.0", category="product",
            parameters={"type": "object", "properties": {"dry_run": {"type": "boolean", "default": True}}},
            required_permissions=["system.write"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        result = self._control.optimize(dry_run=params.get("dry_run", True))
        if not result.get("success"):
            return ToolResult.fail(result.get("error", "Optimization failed"), tool_id="product.control.optimize")
        return ToolResult.ok(data=result, tool_id="product.control.optimize")


class ProductFreeResourcesTool(_ProductTool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="product.control.free_resources", name="Free Resources",
            description="Preview or terminate only allowlisted background processes.",
            version="1.0.0", category="product",
            parameters={"type": "object", "properties": {"commit": {"type": "boolean", "default": False}}},
            required_permissions=["system.write"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        result = self._control.free_resources(commit=params.get("commit", False))
        if not result.get("success"):
            return ToolResult.fail(result.get("error", "Free resources failed"), tool_id="product.control.free_resources")
        return ToolResult.ok(data=result, tool_id="product.control.free_resources")


class ProductCreateProfileTool(_ProductTool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="product.control.create_profile", name="Create State Profile",
            description="Create a restorable system-state profile.", version="1.0.0", category="product",
            parameters={"type": "object", "properties": {"name": {"type": "string"}}},
            required_permissions=["system.write"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        result = self._control.create_profile(name=params.get("name", ""))
        if not result.get("success"):
            return ToolResult.fail(result.get("error", "Profile creation failed"), tool_id="product.control.create_profile")
        return ToolResult.ok(data=result, tool_id="product.control.create_profile")
