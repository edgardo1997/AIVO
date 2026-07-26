import asyncio
import json
import logging
from typing import Any, Dict, List, Optional
from sentinel.conversation import ConversationRequest
from sentinel.core.tool import Tool, ToolResult, ToolSpec
from sentinel.presentation import PresentationLayer, PresentationMode

log = logging.getLogger("sentinel.chat_tools")
_presentation = PresentationLayer()


def _get_orchestrator():
    from modules import get_sentinel_orchestrator

    return get_sentinel_orchestrator()


def _get_ai_service():
    from modules.ai_provider import _svc

    return _svc


def _get_presentation():
    return _presentation


def _persist_turn(
    user_id: str,
    session_id: Optional[str],
    prompt: str,
    response: str,
    *,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    pipeline: Optional[Dict[str, Any]] = None,
) -> None:
    if not session_id or not response:
        return
    import uuid
    from datetime import datetime, timezone
    from modules.sentinel_bridge_helpers import _conversation_db

    message: Dict[str, Any] = {
        "id": uuid.uuid4().hex,
        "prompt": prompt[:100_000],
        "response": response[:100_000],
        "pipeline": pipeline,
    }
    if provider:
        message["provider"] = provider[:500]
    if model:
        message["model"] = model[:500]
    _conversation_db().append_conversation_message(
        user_id=user_id,
        session_id=session_id,
        title=prompt[:70] or "Nueva operación",
        message=message,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


def _build_trace_from_result(result) -> Dict[str, Any]:
    plan = result.plan
    step_count = len(plan.plan.steps) if plan.plan and plan.plan.steps else 0
    context_factors = result.decision.context_factors if result.decision else []
    decision_block = (
        {
            "decision": result.decision.decision if result.decision else None,
            "base_risk_score": result.decision.base_risk_score if result.decision else None,
            "context_modifier": result.decision.context_modifier if result.decision else None,
            "final_risk_score": result.decision.final_risk_score if result.decision else None,
            "reason": result.decision.reason if result.decision else None,
            "context_factors": context_factors,
        }
        if result.decision
        else None
    )
    return {
        "presentation": _presentation.present(result, PresentationMode.USER),
        "intent": {
            "action": plan.intent.action,
            "target": plan.intent.target,
            "confidence": plan.intent.confidence,
            "raw_input": plan.intent.raw_input,
        },
        "plan": {"steps": step_count},
        "decision": decision_block,
        "grounding_results": result.grounding_results or [],
        "grounding_satisfied": result.grounding_satisfied,
        "advisory": result.advisory.to_dict() if result.advisory else None,
        "tool_result": {
            "success": result.tool_result.success if result.tool_result else None,
            "tool_id": result.tool_result.tool_id if result.tool_result else None,
        }
        if result.tool_result
        else None,
        "simulated": result.simulated,
        "approved": result.approved,
        "blocked": result.blocked,
        "action_id": result.action_id,
        "simulation_summary": result.simulation_summary,
        "error": result.error,
    }


def _build_summary_from_result(result) -> str:
    plan = result.plan
    intent = plan.intent
    decision = result.decision
    tool_result = result.tool_result
    parts = [
        f"Intent: {intent.action} -> {intent.target} (confidence={intent.confidence:.2f})",
    ]
    if decision:
        parts.append(f"Decision: {decision.decision} (risk={decision.final_risk_score:.2f}, reason={decision.reason})")
    if tool_result:
        status = "success" if tool_result.success else f"error: {tool_result.error}"
        parts.append(f"Tool: {tool_result.tool_id} -> {status}")
    return " | ".join(parts)


class ChatRespondTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="chat.respond",
            name="Chat Respond",
            description="Process a user message through the full orchestration pipeline and return a governed response",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "User message"},
                    "context": {"type": "array", "description": "Conversation history"},
                    "session_id": {"type": "string", "description": "Optional conversation session id"},
                },
                "required": ["message"],
            },
            required_permissions=["chat.respond"],
            timeout_seconds=60,
            category="orchestrator",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            orch = _get_orchestrator()
            ai_svc = _get_ai_service()
            identity = context.get("identity", {})
            message = params.get("message", "")
            history = params.get("context", [])
            raw_session_id = params.get("session_id")

            if not message:
                return ToolResult.ok(
                    data={
                        "response": "Please provide a message.",
                        "provider": None,
                        "model": None,
                        "pipeline": None,
                        "conversation_mode": "core",
                        "capabilities": ai_svc.conversation_capabilities(),
                    },
                    tool_id="chat.respond",
                )

            session_id = None
            if raw_session_id:
                import re

                value = str(raw_session_id).strip()
                if re.match(r"^[A-Za-z0-9._-]{1,80}$", value):
                    session_id = value

            result = None
            pipeline_summary = "No orchestration context is available for this turn."
            pipeline_trace = None
            actionable = False

            preflight_intent = orch.classify_intent(message)
            requires_pipeline = preflight_intent.confidence >= 0.6

            if not requires_pipeline:
                pipeline_trace = {
                    "intent": {
                        "action": preflight_intent.action,
                        "target": preflight_intent.target,
                        "confidence": preflight_intent.confidence,
                        "raw_input": preflight_intent.raw_input,
                    },
                    "decision": None,
                    "advisory": None,
                    "tool_result": None,
                    "simulated": False,
                    "approved": False,
                    "blocked": False,
                    "action_id": None,
                    "simulation_summary": None,
                    "error": None,
                }
                pipeline_summary = (
                    "Conversation-only route selected: no executable system intent was detected, "
                    "so no tool was planned or authorized."
                )

            if requires_pipeline:
                result = await asyncio.wait_for(
                    orch.process(message, identity=identity, session_id=session_id),
                    timeout=15,
                )
                intent = result.plan.intent
                pipeline_summary = _build_summary_from_result(result)
                pipeline_trace = _build_trace_from_result(result)
                actionable = intent.confidence >= 0.6

            _AI_TIMEOUT = 48
            conversation_mode = "core"
            conversation_capabilities = ai_svc.conversation_capabilities()
            response_text = ""
            provider = None
            model = None

            if actionable and result:
                governed_response = _presentation.summary(result)
                if governed_response:
                    _persist_turn(
                        identity.get("user_id", ""),
                        session_id,
                        message,
                        governed_response,
                        provider="sentinel_core",
                        pipeline=pipeline_trace,
                    )
                    return ToolResult.ok(
                        data={
                            "response": governed_response,
                            "provider": "sentinel_core",
                            "model": None,
                            "pipeline": pipeline_trace,
                            "conversation_mode": "core",
                            "capabilities": conversation_capabilities,
                        },
                        tool_id="chat.respond",
                    )

                tool_data = result.tool_result.data if result.tool_result else None
                ctx = list(history) if history else []
                if ctx:
                    ctx.append({"role": "system", "content": f"Pipeline analysis:\n{pipeline_summary}"})
                try:
                    fmt_response = await asyncio.wait_for(
                        asyncio.to_thread(
                            ai_svc.chat,
                            message=f"User said: {message}\n\nTool result:\n{json.dumps(tool_data, indent=2) if tool_data else '(empty)'}",
                            context=ctx or None,
                            system_prompt="You are Sentinel, an intelligent PC orchestration assistant. The system executed a tool based on the user's request. Format the tool result as a concise, natural response to the user. Be direct and helpful.",
                            purpose="tool_result",
                            tool_result=tool_data,
                        ),
                        timeout=_AI_TIMEOUT,
                    )
                    response_text = fmt_response.get("response", "")
                    provider = fmt_response.get("provider")
                    model = fmt_response.get("model")
                    conversation_mode = fmt_response.get("conversation_mode", "core")
                    conversation_capabilities = fmt_response.get("capabilities", conversation_capabilities)
                except (asyncio.TimeoutError, Exception):
                    log.exception("Result formatting failed; using core conversation")
                    core = ai_svc._conversation.respond(
                        ConversationRequest(message=message, purpose="tool_result", tool_result=tool_data)
                    ).to_dict()
                    response_text, provider, model = core["response"], None, None
                    conversation_mode, conversation_capabilities = core["conversation_mode"], core["capabilities"]
            else:
                ctx = list(history) if history else []
                enrich_ctx = list(ctx)
                enrich_ctx.append({"role": "system", "content": f"Sentinel pipeline context:\n{pipeline_summary}"})
                try:
                    chat_response = await asyncio.wait_for(
                        asyncio.to_thread(
                            ai_svc.chat,
                            message=message,
                            context=enrich_ctx,
                            system_prompt=(
                                "You are Sentinel, an intelligent PC orchestration assistant integrated into AIVO. "
                                "Your purpose is to help the user with system monitoring, file management, task "
                                "execution, and general computer assistance. You have access to system resources "
                                "and can execute commands. Be concise, accurate, and helpful. "
                                "If the user asks about their PC or system, use the pipeline context above to answer."
                            ),
                        ),
                        timeout=_AI_TIMEOUT,
                    )
                    response_text = chat_response.get("response", "")
                    provider = chat_response.get("provider")
                    model = chat_response.get("model")
                    conversation_mode = chat_response.get("conversation_mode", conversation_mode)
                    conversation_capabilities = chat_response.get("capabilities", conversation_capabilities)
                except (asyncio.TimeoutError, Exception):
                    log.exception("Chat integration failed; using core conversation")
                    core = ai_svc._conversation.respond(ConversationRequest(message=message, context=ctx)).to_dict()
                    response_text, provider, model = core["response"], None, None
                    conversation_mode, conversation_capabilities = core["conversation_mode"], core["capabilities"]

            _persist_turn(
                identity.get("user_id", ""),
                session_id,
                message,
                response_text,
                provider=provider,
                model=model,
                pipeline=pipeline_trace,
            )

            return ToolResult.ok(
                data={
                    "response": response_text,
                    "provider": provider,
                    "model": model,
                    "pipeline": pipeline_trace,
                    "conversation_mode": conversation_mode,
                    "capabilities": conversation_capabilities,
                },
                tool_id="chat.respond",
            )

        except Exception as e:
            log.exception("chat.respond failed")
            return ToolResult.fail(error=str(e), tool_id="chat.respond")
