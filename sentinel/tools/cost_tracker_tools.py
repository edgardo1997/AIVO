import logging
from typing import Any, Dict, Optional

from sentinel.core.tool import Tool, ToolResult, ToolSpec

logger = logging.getLogger(__name__)


def _get_ct():
    from modules import get_sentinel_orchestrator
    orch = get_sentinel_orchestrator()
    return getattr(orch, "cost_tracker", None)


class BudgetCreateTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="budget.create",
            name="Create Budget",
            description="Create a cost budget.",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "max_cost_usd": {"type": "number"},
                    "period": {"type": "string"},
                    "provider_id": {"type": "string"},
                    "max_tokens": {"type": "integer"},
                    "enabled": {"type": "boolean"},
                },
                "required": ["name", "max_cost_usd"],
            },
            required_permissions=["permissions.admin"],
            category="cost",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        ct = _get_ct()
        if ct is None:
            return ToolResult.fail(error="Cost tracker not available", tool_id="budget.create")
        from sentinel.core.cost_tracker import BudgetConfig
        ct.set_budget(BudgetConfig(
            name=params["name"],
            max_cost_usd=float(params.get("max_cost_usd", 0)),
            period=params.get("period", "monthly"),
            provider_id=params.get("provider_id"),
            max_tokens=params.get("max_tokens"),
            enabled=params.get("enabled", True),
        ))
        return ToolResult.ok(data={"success": True, "name": params["name"]}, tool_id="budget.create")


class BudgetDeleteTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="budget.delete",
            name="Delete Budget",
            description="Delete a cost budget by name.",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                },
                "required": ["name"],
            },
            required_permissions=["permissions.admin"],
            category="cost",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        ct = _get_ct()
        if ct is None:
            return ToolResult.fail(error="Cost tracker not available", tool_id="budget.delete")
        ct.delete_budget(params["name"])
        return ToolResult.ok(data={"success": True}, tool_id="budget.delete")
