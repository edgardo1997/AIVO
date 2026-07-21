import logging
from typing import Any, Dict, Optional

from sentinel.core.agent import AgentRegistry, AgentSpec, AgentStatus
from sentinel.core.tool import Tool, ToolResult, ToolSpec

logger = logging.getLogger(__name__)


class AgentListTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="agent.list",
            name="List Agents",
            description="List all registered agents with their status and capabilities",
            version="1.0.0",
            category="agent",
            parameters={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "Filter by status (active, idle, error, disabled)",
                    },
                },
            },
            required_permissions=["system.read"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        registry: Optional[AgentRegistry] = (context or {}).get("_agent_registry")
        if registry is None:
            return ToolResult.ok(data={"agents": [], "total": 0}, tool_id="agent.list")
        status_filter = params.get("status")
        if status_filter:
            agents = [a for a in registry.list_all() if a.status.value == status_filter]
        else:
            agents = registry.list_all()
        return ToolResult.ok(
            data={
                "agents": [a.to_dict() for a in agents],
                "total": len(agents),
            },
            tool_id="agent.list",
        )


class AgentCreateTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="agent.create",
            name="Create Agent",
            description="Register a new agent with provider, model, and capabilities",
            version="1.0.0",
            category="agent",
            parameters={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Unique agent identifier"},
                    "name": {"type": "string", "description": "Human-readable name"},
                    "description": {"type": "string", "description": "Description of the agent's purpose"},
                    "provider": {"type": "string", "description": "AI provider (e.g. ollama, openrouter)"},
                    "model": {"type": "string", "description": "Model identifier"},
                    "capabilities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of capability IDs this agent can handle",
                    },
                    "allowed_tools": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tool IDs this agent is allowed to use",
                    },
                    "system_prompt": {"type": "string", "description": "System prompt for the agent"},
                },
            },
            required_permissions=["permissions.admin"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        registry: Optional[AgentRegistry] = (context or {}).get("_agent_registry")
        if registry is None:
            return ToolResult.fail("Agent registry not available", tool_id="agent.create")
        agent_id = params.get("id")
        if not agent_id:
            return ToolResult.fail("Agent id is required", tool_id="agent.create")
        if registry.get(agent_id):
            return ToolResult.fail(f"Agent '{agent_id}' already exists", tool_id="agent.create")
        try:
            status = AgentStatus(params["status"]) if "status" in params else AgentStatus.IDLE
        except ValueError:
            return ToolResult.fail(f"Invalid status: {params['status']}", tool_id="agent.create")
        agent = AgentSpec(
            id=agent_id,
            name=params.get("name", agent_id),
            description=params.get("description", ""),
            provider=params.get("provider", "ollama"),
            model=params.get("model", ""),
            capabilities=params.get("capabilities", []),
            allowed_tools=params.get("allowed_tools", []),
            system_prompt=params.get("system_prompt", ""),
            status=status,
        )
        registry.register(agent, persist=True)
        logger.info("Agent '%s' created (provider=%s, model=%s)", agent_id, agent.provider, agent.model)
        return ToolResult.ok(data={"agent": agent.to_dict(), "status": "created"}, tool_id="agent.create")


class AgentDeleteTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="agent.delete",
            name="Delete Agent",
            description="Remove a registered agent",
            version="1.0.0",
            category="agent",
            parameters={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Agent identifier to delete"},
                },
                "required": ["id"],
            },
            required_permissions=["permissions.admin"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        registry: Optional[AgentRegistry] = (context or {}).get("_agent_registry")
        if registry is None:
            return ToolResult.fail("Agent registry not available", tool_id="agent.delete")
        agent_id = params.get("id")
        if not agent_id:
            return ToolResult.fail("Agent id is required", tool_id="agent.delete")
        try:
            registry.unregister(agent_id, persist=True)
            return ToolResult.ok(data={"status": "deleted", "agent_id": agent_id}, tool_id="agent.delete")
        except KeyError as e:
            return ToolResult.fail(str(e), tool_id="agent.delete")


class AgentUpdateTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="agent.update",
            name="Update Agent",
            description="Update an existing agent's configuration fields",
            version="1.0.0",
            category="agent",
            parameters={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Agent identifier to update"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "provider": {"type": "string"},
                    "model": {"type": "string"},
                    "capabilities": {"type": "array", "items": {"type": "string"}},
                    "allowed_tools": {"type": "array", "items": {"type": "string"}},
                    "system_prompt": {"type": "string"},
                    "status": {"type": "string", "enum": ["idle", "active", "busy", "error", "disabled"]},
                },
                "required": ["id"],
            },
            required_permissions=["permissions.admin"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        registry: Optional[AgentRegistry] = (context or {}).get("_agent_registry")
        if registry is None:
            return ToolResult.fail("Agent registry not available", tool_id="agent.update")
        agent_id = params.get("id")
        if not agent_id:
            return ToolResult.fail("Agent id is required", tool_id="agent.update")
        if registry.get(agent_id) is None:
            return ToolResult.fail(f"Agent '{agent_id}' not found", tool_id="agent.update")
        updates = {k: v for k, v in params.items() if k != "id" and v is not None}
        if not updates:
            return ToolResult.fail("No fields to update", tool_id="agent.update")
        try:
            agent = registry.update(agent_id, persist=True, **updates)
            return ToolResult.ok(data={"agent": agent.to_dict(), "status": "updated"}, tool_id="agent.update")
        except Exception as e:
            return ToolResult.fail(str(e), tool_id="agent.update")


class AgentDelegateTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="agent.delegate",
            name="Delegate to Agent",
            description="Delegate a task to an agent. Specify agent_id for a specific agent, or omit for auto-selection by strategy.",
            version="1.0.0",
            category="agent",
            parameters={
                "type": "object",
                "properties": {
                    "agent_id": {"type": "string", "description": "Target agent identifier (omit for auto-select)"},
                    "task": {"type": "string", "description": "Task description to delegate"},
                    "context": {
                        "type": "object",
                        "description": "Context data to pass to the agent",
                    },
                    "strategy": {
                        "type": "string",
                        "enum": ["auto", "local", "powerful"],
                        "description": "Model selection strategy: auto (smart default), local (prefer local models), powerful (prefer most capable)",
                    },
                },
                "required": ["task"],
            },
            required_permissions=["ai.chat"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        registry: Optional[AgentRegistry] = (context or {}).get("_agent_registry")
        if registry is None:
            return ToolResult.fail("Agent registry not available", tool_id="agent.delegate")
        task = params.get("task", "")
        if not task:
            return ToolResult.fail("Task is required", tool_id="agent.delegate")
        agent_id = params.get("agent_id")
        strategy = params.get("strategy", "auto")
        task_context = params.get("context", {})

        try:
            agent = registry.resolve_agent(agent_id=agent_id, task=task, strategy=strategy)
        except KeyError as e:
            return ToolResult.fail(str(e), tool_id="agent.delegate")

        if agent.status == AgentStatus.DISABLED:
            return ToolResult.fail(f"Agent '{agent.id}' is disabled", tool_id="agent.delegate")
        logger.info(
            "Delegating task to agent '%s' (provider=%s, model=%s, strategy=%s): %s",
            agent.id,
            agent.provider,
            agent.model,
            strategy,
            task[:100],
        )
        result = registry.execute_agent(agent.id, task, task_context)
        if result.get("error"):
            return ToolResult(
                success=False,
                error=result["error"],
                data=result,
                tool_id="agent.delegate",
            )
        return ToolResult.ok(data=result, tool_id="agent.delegate")
