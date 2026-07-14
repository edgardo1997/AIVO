import logging
from typing import Any, Dict, Optional

from sentinel.core.trigger import TriggerEngine, TriggerCondition, TriggerAction, TriggerRule
from sentinel.core.tool import Tool, ToolResult, ToolSpec

logger = logging.getLogger(__name__)


class TriggerListTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="trigger.list",
            name="List Triggers",
            description="List all configured trigger rules",
            version="0.1.0",
            category="trigger",
            parameters={},
            required_permissions=["system.read"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        engine: Optional[TriggerEngine] = (context or {}).get("_trigger_engine")
        if engine is None:
            return ToolResult.ok(data={"triggers": [], "total": 0}, tool_id="trigger.list")
        return ToolResult.ok(data={
            "triggers": [r.to_dict() for r in engine.list_rules()],
            "total": engine.count(),
        }, tool_id="trigger.list")


class TriggerCreateTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="trigger.create",
            name="Create Trigger",
            description="Create a new trigger rule that fires when conditions are met",
            version="0.1.0",
            category="trigger",
            parameters={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Unique trigger identifier"},
                    "name": {"type": "string", "description": "Human-readable name"},
                    "description": {"type": "string", "description": "Description of what the trigger does"},
                    "conditions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "metric": {"type": "string", "description": "Metric name (e.g. cpu_percent, memory_percent)"},
                                "operator": {"type": "string", "enum": ["gt", "lt", "gte", "lte", "eq", "neq"]},
                                "value": {"type": "number"},
                            },
                        },
                    },
                    "action": {
                        "type": "object",
                        "properties": {
                            "tool_id": {"type": "string"},
                            "params": {"type": "object"},
                        },
                    },
                    "cooldown_seconds": {"type": "integer", "description": "Minimum seconds between firings"},
                    "enabled": {"type": "boolean"},
                },
                "required": ["id", "conditions"],
            },
            required_permissions=["permissions.admin"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        engine: Optional[TriggerEngine] = (context or {}).get("_trigger_engine")
        if engine is None:
            return ToolResult.err("Trigger engine not available", tool_id="trigger.create")
        rule_id = params.get("id")
        if not rule_id:
            return ToolResult.err("Trigger id is required", tool_id="trigger.create")
        if engine.get_rule(rule_id):
            return ToolResult.err(f"Trigger '{rule_id}' already exists", tool_id="trigger.create")
        conditions = [TriggerCondition.from_dict(c) for c in params.get("conditions", [])]
        if not conditions:
            return ToolResult.err("At least one condition is required", tool_id="trigger.create")
        action_data = params.get("action")
        action = TriggerAction.from_dict(action_data) if action_data else None
        rule = TriggerRule(
            id=rule_id,
            name=params.get("name", rule_id),
            description=params.get("description", ""),
            conditions=conditions,
            action=action,
            cooldown_seconds=params.get("cooldown_seconds", 300),
            enabled=params.get("enabled", True),
        )
        engine.add_rule(rule)
        logger.info("Trigger '%s' created with %d condition(s)", rule_id, len(conditions))
        return ToolResult.ok(data={"trigger": rule.to_dict(), "status": "created"}, tool_id="trigger.create")


class TriggerDeleteTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="trigger.delete",
            name="Delete Trigger",
            description="Remove a trigger rule by id",
            version="0.1.0",
            category="trigger",
            parameters={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Trigger identifier to delete"},
                },
                "required": ["id"],
            },
            required_permissions=["permissions.admin"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        engine: Optional[TriggerEngine] = (context or {}).get("_trigger_engine")
        if engine is None:
            return ToolResult.err("Trigger engine not available", tool_id="trigger.delete")
        rule_id = params.get("id")
        if not rule_id:
            return ToolResult.err("Trigger id is required", tool_id="trigger.delete")
        try:
            engine.remove_rule(rule_id)
            return ToolResult.ok(data={"status": "deleted", "trigger_id": rule_id}, tool_id="trigger.delete")
        except KeyError as e:
            return ToolResult.err(str(e), tool_id="trigger.delete")


class TriggerHistoryTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="trigger.history",
            name="Trigger History",
            description="View history of trigger firings",
            version="0.1.0",
            category="trigger",
            parameters={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max records to return"},
                },
            },
            required_permissions=["system.read"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        engine: Optional[TriggerEngine] = (context or {}).get("_trigger_engine")
        if engine is None:
            return ToolResult.ok(data={"history": [], "total": 0}, tool_id="trigger.history")
        limit = params.get("limit", 20)
        history = engine.get_history(limit=limit)
        return ToolResult.ok(data={
            "history": [h.to_dict() for h in history],
            "total": len(history),
        }, tool_id="trigger.history")


class TriggerEvaluateTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="trigger.evaluate",
            name="Evaluate Triggers",
            description="Evaluate all triggers against current metrics and fire any matching",
            version="0.1.0",
            category="trigger",
            parameters={
                "type": "object",
                "properties": {
                    "metrics": {
                        "type": "object",
                        "description": "Current metric values (e.g. {\"cpu_percent\": 85, \"memory_percent\": 70})",
                        "additionalProperties": {"type": "number"},
                    },
                },
                "required": ["metrics"],
            },
            required_permissions=["permissions.admin"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        engine: Optional[TriggerEngine] = (context or {}).get("_trigger_engine")
        if engine is None:
            return ToolResult.err("Trigger engine not available", tool_id="trigger.evaluate")
        metrics = params.get("metrics", {})
        if not metrics:
            return ToolResult.err("metrics object is required", tool_id="trigger.evaluate")
        fires = engine.evaluate(metrics)
        return ToolResult.ok(data={
            "fires": [f.to_dict() for f in fires],
            "total_fired": len(fires),
        }, tool_id="trigger.evaluate")
