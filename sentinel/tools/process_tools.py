from typing import Any, Dict
from sentinel.core.tool import Tool, ToolResult, ToolSpec
from sentinel.presentation import PresentationLayer, PresentationMode

_presentation = PresentationLayer()


def _get_orchestrator():
    from modules import get_sentinel_orchestrator
    return get_sentinel_orchestrator()


def _validate_conversation_id(session_id: str) -> str:
    import re
    value = str(session_id).strip()
    if not re.match(r"^[A-Za-z0-9._-]{1,80}$", value):
        raise ValueError("Invalid conversation id")
    return value


class ProcessTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="process.execute",
            name="Process Utterance",
            description="Process a user utterance through the orchestrator pipeline",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "utterance": {"type": "string", "description": "User input"},
                    "session_id": {"type": "string", "description": "Optional conversation session id"},
                    "dry_run": {"type": "boolean", "description": "Skip execution"},
                    "presentation_mode": {"type": "string", "description": "Presentation mode (user|developer|raw)"},
                },
                "required": ["utterance"],
            },
            required_permissions=["process.execute"],
            timeout_seconds=60,
            category="orchestrator",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            orch = _get_orchestrator()
            utterance = params.get("utterance", "")
            if not utterance:
                return ToolResult.fail(error="utterance is required", tool_id="process.execute")
            raw_session_id = params.get("session_id")
            session_id = None
            if raw_session_id:
                try:
                    session_id = _validate_conversation_id(raw_session_id)
                except ValueError:
                    return ToolResult.fail(error="Invalid conversation id", tool_id="process.execute")
            dry_run = params.get("dry_run", False)
            presentation_mode = PresentationMode.parse(params.get("presentation_mode"))
            identity = context.get("identity", {})
            result = await orch.process(
                utterance,
                identity=identity,
                session_id=session_id,
                dry_run=dry_run,
            )
            plan = result.plan
            goal_meta = None
            if plan.plan.goal:
                goal_meta = {
                    "id": plan.plan.goal.id,
                    "priority": plan.plan.goal.priority,
                    "possible_capabilities": plan.plan.goal.possible_capabilities,
                }
            data = {
                "presentation": result.presentation if result.presentation is not None
                    else _presentation.present(result, presentation_mode),
                "simulated": result.simulated,
                "approved": result.approved,
                "blocked": result.blocked,
                "action_id": result.action_id,
                "simulation_summary": result.simulation_summary,
                "error": result.error,
                "decision": result.decision.decision if result.decision else None,
                "decision_reason": result.decision.reason if result.decision else None,
                "goal": goal_meta,
                "intent": {
                    "action": plan.intent.action,
                    "target": plan.intent.target,
                    "parameters": plan.intent.parameters,
                    "confidence": plan.intent.confidence,
                    "raw_input": plan.intent.raw_input,
                },
                "context_factors": result.decision.context_factors if result.decision else [],
                "base_risk_score": result.decision.base_risk_score if result.decision else None,
                "context_modifier": result.decision.context_modifier if result.decision else None,
                "final_risk_score": result.decision.final_risk_score if result.decision else None,
                "plan": {
                    "risk_score": plan.plan.risk_score,
                    "steps": [
                        {
                            "id": s.id,
                            "tool_id": s.tool_id,
                            "description": s.description,
                            "estimated_impact": s.estimated_impact,
                            "is_reversible": s.is_reversible,
                            "depends_on": s.depends_on,
                        }
                        for s in plan.plan.steps
                    ],
                },
                "tool_result": {
                    "success": result.tool_result.success if result.tool_result else None,
                    "data": result.tool_result.data if result.tool_result else None,
                    "error": result.tool_result.error if result.tool_result else None,
                    "requires_confirmation": result.tool_result.requires_confirmation if result.tool_result else False,
                    "duration_ms": result.tool_result.duration_ms if result.tool_result else None,
                }
                if result.tool_result
                else None,
                "step_results": [_step_result(s) for s in result.step_results] if result.step_results else None,
                "rollback_actions": result.rollback_actions,
                "advisory": result.advisory.to_dict() if result.advisory else None,
                "grounding_results": result.grounding_results,
                "grounding_satisfied": result.grounding_satisfied,
            }
            return ToolResult.ok(data=data, tool_id="process.execute")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="process.execute")


def _step_result(step) -> Dict[str, Any]:
    return {
        "step_id": step.step_id,
        "tool_id": step.tool_id,
        "success": step.success,
        "data": step.data,
        "error": step.error,
        "duration_ms": step.duration_ms,
        "attempts": step.attempts,
        "recovery_strategy": step.recovery_strategy,
        "executed_tool_id": step.executed_tool_id,
        "status": step.status,
    }


class MultiAgentProcessTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="process.multi_agent",
            name="Multi-Agent Process",
            description="Process a user utterance through the multi-agent orchestrator",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "utterance": {"type": "string", "description": "User input"},
                    "session_id": {"type": "string", "description": "Optional conversation session id"},
                },
                "required": ["utterance"],
            },
            required_permissions=["process.execute"],
            timeout_seconds=120,
            category="orchestrator",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            orch = _get_orchestrator()
            utterance = params.get("utterance", "")
            if not utterance:
                return ToolResult.fail(error="utterance is required", tool_id="process.multi_agent")
            session_id = params.get("session_id")
            identity = context.get("identity", {})
            result = await orch.process_multi_agent(
                utterance,
                identity=identity,
                session_id=session_id,
            )
            data = {
                "success": result.tool_result.success if result.tool_result else False,
                "error": result.error,
                "grounding_results": result.grounding_results,
                "grounding_satisfied": result.grounding_satisfied,
                "sub_task_results": [
                    {
                        "sub_task_id": s.step_id,
                        "success": s.success,
                        "error": s.error,
                        "duration_ms": s.duration_ms,
                    }
                    for s in result.step_results
                ]
                if result.step_results
                else [],
            }
            return ToolResult.ok(data=data, tool_id="process.multi_agent")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="process.multi_agent")
