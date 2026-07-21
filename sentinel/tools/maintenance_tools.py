import logging
from typing import Any, Dict, Optional

from sentinel.core.tool import Tool, ToolResult, ToolSpec

logger = logging.getLogger(__name__)


def _get_orch():
    from modules import get_sentinel_orchestrator
    return get_sentinel_orchestrator()


class CacheClearTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="cache.clear",
            name="Clear Plan Cache",
            description="Clear the plan cache.",
            version="1.0.0",
            parameters={},
            required_permissions=["permissions.admin"],
            category="maintenance",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        orch = _get_orch()
        pc = getattr(orch, "plan_cache", None)
        if pc is None:
            return ToolResult.ok(data={"cleared": False}, tool_id="cache.clear")
        count = pc.clear()
        return ToolResult.ok(data={"cleared": True, "entries_removed": count}, tool_id="cache.clear")


class RateLimiterClearTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="rate_limiter.clear",
            name="Clear Rate Limiter",
            description="Clear all rate limiter buckets.",
            version="1.0.0",
            parameters={},
            required_permissions=["permissions.admin"],
            category="maintenance",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        orch = _get_orch()
        rl = getattr(orch, "_rate_limiter", None)
        if rl is None:
            return ToolResult.ok(data={"cleared": False}, tool_id="rate_limiter.clear")
        count = rl.clear()
        return ToolResult.ok(data={"cleared": True, "buckets_removed": count}, tool_id="rate_limiter.clear")


class FallbackResetStatsTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="fallback.reset_stats",
            name="Reset Fallback Stats",
            description="Reset model router fallback statistics.",
            version="1.0.0",
            parameters={},
            required_permissions=["permissions.admin"],
            category="maintenance",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        orch = _get_orch()
        mr = getattr(orch, "_model_router", None)
        if mr is None:
            return ToolResult.ok(data={"reset": 0}, tool_id="fallback.reset_stats")
        count = mr.reset_fallback_stats()
        return ToolResult.ok(data={"reset": count}, tool_id="fallback.reset_stats")


class ModelCircuitBreakerResetTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="circuit_breaker.reset_model",
            name="Reset Model Circuit Breaker",
            description="Reset circuit breaker for a specific model provider or all.",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "provider_id": {"type": "string", "description": "Provider ID (empty = all)"},
                },
                "required": [],
            },
            required_permissions=["permissions.admin"],
            category="maintenance",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        orch = _get_orch()
        mr = getattr(orch, "_model_router", None)
        if mr is None:
            return ToolResult.ok(data={"reset": 0, "provider_id": params.get("provider_id")}, tool_id="circuit_breaker.reset_model")
        total = mr.circuit_breaker.reset(provider_id=params.get("provider_id"))
        return ToolResult.ok(data={"reset": total, "provider_id": params.get("provider_id")}, tool_id="circuit_breaker.reset_model")


class ToolCircuitBreakerResetTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="circuit_breaker.reset_tool",
            name="Reset Tool Circuit Breaker",
            description="Reset circuit breaker for a specific tool or resource.",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "resource_type": {"type": "string", "enum": ["model", "tool"]},
                    "resource_id": {"type": "string"},
                },
                "required": ["resource_type", "resource_id"],
            },
            required_permissions=["permissions.admin"],
            category="maintenance",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        orch = _get_orch()
        resource_type = params.get("resource_type", "")
        resource_id = params.get("resource_id", "")
        if resource_type == "model":
            mr = getattr(orch, "_model_router", None)
            count = mr.circuit_breaker.reset(resource_id) if mr else 0
        else:
            h = getattr(orch, "_hardening", None)
            count = h.circuit_breaker.reset(resource_id) if h else 0
        return ToolResult.ok(data={"resource_type": resource_type, "resource_id": resource_id, "circuits_reset": count}, tool_id="circuit_breaker.reset_tool")


class OfflineQueueSyncTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="offline_queue.sync",
            name="Sync Offline Queue",
            description="Process all pending items in the offline queue.",
            version="1.0.0",
            parameters={},
            required_permissions=["permissions.admin"],
            category="maintenance",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        orch = _get_orch()
        stats = await orch._process_offline_queue()
        return ToolResult.ok(data=stats, tool_id="offline_queue.sync")


class OfflineQueueClearTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="offline_queue.clear",
            name="Clear Offline Queue",
            description="Clear items from the offline queue.",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "status": {"type": "string", "description": "Filter by status"},
                },
                "required": [],
            },
            required_permissions=["permissions.admin"],
            category="maintenance",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        orch = _get_orch()
        q = getattr(orch, "_offline_queue", None)
        if q is None:
            return ToolResult.ok(data={"cleared": 0}, tool_id="offline_queue.clear")
        from sentinel.core.offline_queue import QueueStatus
        st = QueueStatus(params["status"]) if params.get("status") else None
        count = q.clear(status=st)
        return ToolResult.ok(data={"cleared": count}, tool_id="offline_queue.clear")


class AlertAcknowledgeTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="alert.acknowledge",
            name="Acknowledge Alert",
            description="Acknowledge one or all alerts.",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "alert_id": {"type": "string", "description": "Specific alert ID, or empty to acknowledge by source"},
                    "source": {"type": "string", "description": "Source to acknowledge all for (used when alert_id is empty)"},
                },
                "required": [],
            },
            required_permissions=["permissions.admin"],
            category="alerts",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        orch = _get_orch()
        am = getattr(orch, "_alert_manager", None)
        if am is None:
            return ToolResult.ok(data={"acknowledged": 0}, tool_id="alert.acknowledge")
        alert_id = params.get("alert_id", "")
        if alert_id:
            ok = am.acknowledge(alert_id)
            return ToolResult.ok(data={"acknowledged": 1 if ok else 0}, tool_id="alert.acknowledge")
        source = params.get("source")
        count = am.acknowledge_all(source=source)
        return ToolResult.ok(data={"acknowledged": count}, tool_id="alert.acknowledge")


class AlertCheckTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="alert.check",
            name="Check Alerts",
            description="Trigger alert check for all sources.",
            version="1.0.0",
            parameters={},
            required_permissions=["permissions.admin"],
            category="alerts",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        orch = _get_orch()
        am = getattr(orch, "_alert_manager", None)
        if am is None:
            return ToolResult.ok(data={"checked": False}, tool_id="alert.check")
        count = am.check_all()
        return ToolResult.ok(data={"checked": True, "new_alerts": count, "stats": am.stats()}, tool_id="alert.check")


class AlertClearTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="alert.clear",
            name="Clear Alerts",
            description="Clear acknowledged alerts.",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "acknowledged_only": {"type": "boolean", "description": "Only clear acknowledged alerts (default true)"},
                },
                "required": [],
            },
            required_permissions=["permissions.admin"],
            category="alerts",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        orch = _get_orch()
        am = getattr(orch, "_alert_manager", None)
        if am is None:
            return ToolResult.ok(data={"cleared": 0}, tool_id="alert.clear")
        count = am.clear(acknowledged_only=params.get("acknowledged_only", True))
        return ToolResult.ok(data={"cleared": count}, tool_id="alert.clear")


class SimulateApproveTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="simulate.approve",
            name="Approve Execution",
            description="Approve or reject a pending execution by action_id.",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "action_id": {"type": "string"},
                    "approved": {"type": "boolean", "description": "True=approve, False=reject"},
                },
                "required": ["action_id"],
            },
            required_permissions=["system.read"],
            category="simulate",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        orch = _get_orch()
        action_id = params.get("action_id", "")
        approved = params.get("approved", True)
        result = await orch.approve_execution(
            action_id,
            approved=approved,
            approver_identity=context.get("identity", {}),
        )
        from sentinel.presentation import PresentationLayer, PresentationMode
        pres = PresentationLayer()
        plan = result.plan
        return ToolResult.ok(data={
            "presentation": pres.present(result, PresentationMode.USER),
            "blocked": result.blocked,
            "approved": result.approved,
            "action_id": result.action_id,
            "error": result.error,
            "simulation_summary": result.simulation_summary,
            "decision": result.decision.decision if result.decision else None,
            "decision_reason": result.decision.reason if result.decision else None,
            "intent": {"action": plan.intent.action, "target": plan.intent.target, "parameters": plan.intent.parameters, "confidence": plan.intent.confidence, "raw_input": plan.intent.raw_input},
            "tool_result": {"success": result.tool_result.success if result.tool_result else None, "data": result.tool_result.data if result.tool_result else None, "error": result.tool_result.error if result.tool_result else None, "requires_confirmation": result.tool_result.requires_confirmation if result.tool_result else False, "duration_ms": result.tool_result.duration_ms if result.tool_result else None} if result.tool_result else None,
            "step_results": [{"step_id": s.step_id, "tool_id": s.tool_id, "success": s.success, "data": s.data, "error": s.error, "duration_ms": s.duration_ms, "attempts": s.attempts, "recovery_strategy": s.recovery_strategy, "executed_tool_id": s.executed_tool_id, "status": s.status} for s in result.step_results] if result.step_results else None,
            "rollback_actions": result.rollback_actions,
        }, tool_id="simulate.approve")


class SimulateModifyAndApproveTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="simulate.modify_and_approve",
            name="Modify and Approve Execution",
            description="Approve a pending execution with modified steps.",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "action_id": {"type": "string"},
                    "steps": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["action_id", "steps"],
            },
            required_permissions=["system.read"],
            category="simulate",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        orch = _get_orch()
        result = await orch.approve_with_modifications(
            params["action_id"],
            params["steps"],
            approver_identity=context.get("identity", {}),
        )
        from sentinel.presentation import PresentationLayer, PresentationMode
        pres = PresentationLayer()
        return ToolResult.ok(data={
            "presentation": pres.present(result, PresentationMode.USER),
            "blocked": result.blocked,
            "approved": result.approved,
            "action_id": result.action_id,
            "error": result.error,
            "step_results": [{"step_id": s.step_id, "tool_id": s.tool_id, "success": s.success, "data": s.data, "error": s.error, "duration_ms": s.duration_ms, "attempts": s.attempts, "recovery_strategy": s.recovery_strategy, "executed_tool_id": s.executed_tool_id, "status": s.status} for s in result.step_results] if result.step_results else None,
            "rollback_actions": result.rollback_actions,
        }, tool_id="simulate.modify_and_approve")


class ProcessOfflineTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="process.offline",
            name="Process Offline",
            description="Queue an utterance for offline processing.",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "utterance": {"type": "string"},
                    "session_id": {"type": "string"},
                },
                "required": ["utterance"],
            },
            required_permissions=["system.read"],
            category="process",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        orch = _get_orch()
        result = await orch.process_offline(
            params.get("utterance", ""),
            identity=context.get("identity", {}),
            session_id=params.get("session_id"),
        )
        return ToolResult.ok(data={
            "queued": result.action_id is not None,
            "item_id": result.action_id,
            "error": result.error,
        }, tool_id="process.offline")


class SkillSuggestTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="skill.suggest",
            name="Suggest Skill",
            description="Get AI-suggested skills for a task description.",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "Task description"},
                },
                "required": ["task"],
            },
            required_permissions=["system.read"],
            category="skills",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        orch = _get_orch()
        se = getattr(orch, "_skill_engine", None)
        if se is None:
            return ToolResult.fail(error="Skill engine not configured", tool_id="skill.suggest")
        task = params.get("task", "")
        if not task:
            return ToolResult.fail(error="task is required", tool_id="skill.suggest")
        result = await se.suggest(task)
        return ToolResult.ok(data=result, tool_id="skill.suggest")


class SkillExecuteTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="skill.execute",
            name="Execute Skill",
            description="Execute a skill by ID with optional parameters.",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "skill_id": {"type": "string"},
                    "params": {"type": "object"},
                    "session_id": {"type": "string"},
                },
                "required": ["skill_id"],
            },
            required_permissions=["system.read"],
            category="skills",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        orch = _get_orch()
        se = getattr(orch, "_skill_engine", None)
        if se is None:
            return ToolResult.fail(error="Skill engine not configured", tool_id="skill.execute")
        skill_id = params.get("skill_id", "")
        if not skill_id:
            return ToolResult.fail(error="skill_id is required", tool_id="skill.execute")
        skill_params = params.get("params", {})
        context["session_id"] = params.get("session_id")
        result = await se.execute(skill_id, skill_params, context=context)
        return ToolResult.ok(data=result.to_dict(), tool_id="skill.execute")


class AdvisoryFeedbackTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="advisory.feedback",
            name="Record Advisory Feedback",
            description="Record feedback for an advisory insight.",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "helpful": {"type": "boolean"},
                    "insight_kind": {"type": "string"},
                    "execution_id": {"type": "string"},
                },
                "required": [],
            },
            required_permissions=["system.read"],
            category="advisory",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        from modules import get_sentinel_orchestrator
        orch = get_sentinel_orchestrator()
        svc = getattr(orch, "_advisory", None)
        if svc is None:
            return ToolResult.fail(error="Advisory service not available", tool_id="advisory.feedback")
        svc.record_feedback(
            params.get("helpful", False),
            params.get("insight_kind"),
            params.get("execution_id"),
        )
        return ToolResult.ok(data={"status": "ok", "stats": svc.feedback_stats()}, tool_id="advisory.feedback")
