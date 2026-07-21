from typing import Any, Dict
from sentinel.core.tool import Tool, ToolResult, ToolSpec


def _get_registry():
    from modules import get_sentinel_goal_registry
    registry = get_sentinel_goal_registry()
    if registry is None:
        from modules import get_sentinel_orchestrator
        get_sentinel_orchestrator()
        registry = get_sentinel_goal_registry()
    return registry


class GoalRegisterTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="goals.register",
            name="Register Goal",
            description="Register a goal (validate inputs before calling)",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "intent_targets": {"type": "array", "items": {"type": "string"}},
                    "possible_capabilities": {"type": "array", "items": {"type": "string"}},
                    "priority": {"type": "integer"},
                    "base_risk": {"type": "string"},
                    "keywords": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["id", "intent_targets"],
            },
            required_permissions=["goals.admin"],
            timeout_seconds=10,
            category="goals",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            from sentinel.core.goals import GoalDefinition, RiskLevel
            registry = _get_registry()
            if registry is None:
                return ToolResult.fail(error="Goal registry not available", tool_id="goals.register")
            gid = params["id"]
            if registry.get(gid) is not None:
                return ToolResult.fail(error=f"Goal '{gid}' already exists", tool_id="goals.register")
            risk_str = params.get("base_risk", "low")
            goal = GoalDefinition(
                id=gid,
                name=params.get("name", gid),
                description=params.get("description", ""),
                related_intents=params["intent_targets"],
                possible_capabilities=params.get("possible_capabilities", []),
                priority=params.get("priority", 0),
                base_risk=RiskLevel(risk_str),
                keywords=params.get("keywords", []),
            )
            registry.register(goal, source="api")
            return ToolResult.ok(data={"status": "registered", "goal_id": gid}, tool_id="goals.register")
        except ValueError as e:
            return ToolResult.fail(error=str(e), tool_id="goals.register")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="goals.register")


class GoalUnregisterTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="goals.unregister",
            name="Unregister Goal",
            description="Delete a goal from the registry",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "goal_id": {"type": "string"},
                },
                "required": ["goal_id"],
            },
            required_permissions=["goals.admin"],
            timeout_seconds=10,
            category="goals",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            registry = _get_registry()
            if registry is None:
                return ToolResult.fail(error="Goal registry not available", tool_id="goals.unregister")
            registry.unregister(params["goal_id"], source="api")
            return ToolResult.ok(data={"status": "deleted", "goal_id": params["goal_id"]}, tool_id="goals.unregister")
        except KeyError as e:
            return ToolResult.fail(error=str(e), tool_id="goals.unregister")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="goals.unregister")


class GoalUpdateTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="goals.update",
            name="Update Goal",
            description="Update a goal (validate before calling)",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "goal_id": {"type": "string"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "intent_targets": {"type": "array", "items": {"type": "string"}},
                    "possible_capabilities": {"type": "array", "items": {"type": "string"}},
                    "priority": {"type": "integer"},
                    "base_risk": {"type": "string"},
                    "keywords": {"type": "array", "items": {"type": "string"}},
                    "enabled": {"type": "boolean"},
                },
                "required": ["goal_id"],
            },
            required_permissions=["goals.admin"],
            timeout_seconds=10,
            category="goals",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            from sentinel.core.goals import RiskLevel
            registry = _get_registry()
            if registry is None:
                return ToolResult.fail(error="Goal registry not available", tool_id="goals.update")
            goal_id = params.pop("goal_id")
            if registry.get(goal_id) is None:
                return ToolResult.fail(error=f"Goal '{goal_id}' not found", tool_id="goals.update")
            allowed = {
                "name", "description", "intent_targets", "possible_capabilities",
                "priority", "base_risk", "keywords", "enabled",
            }
            changes = {k: v for k, v in params.items() if k in allowed and v is not None}
            if not changes:
                return ToolResult.fail(error="no valid fields to update", tool_id="goals.update")
            if "base_risk" in changes and changes["base_risk"] not in ("low", "medium", "high", "critical"):
                return ToolResult.fail(error=f"invalid base_risk: {changes['base_risk']}", tool_id="goals.update")
            if "base_risk" in changes:
                changes["base_risk"] = RiskLevel(changes["base_risk"])
            registry.update(goal_id, changes, source="api")
            return ToolResult.ok(data={"status": "updated", "goal_id": goal_id}, tool_id="goals.update")
        except (ValueError, KeyError) as e:
            return ToolResult.fail(error=str(e), tool_id="goals.update")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="goals.update")
