import asyncio
import json
import logging
import os
import re
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from modules.auth import IdentityContext, request_identity, require_admin_identity
from sentinel.conversation import ConversationRequest
from sentinel.presentation import PresentationLayer, PresentationMode

log = logging.getLogger("sentinel.sentinel_bridge")
router = APIRouter()
_presentation = PresentationLayer()

_STREAM_END = object()
_STREAM_IDLE_TIMEOUT_SECONDS = 30.0
_CONVERSATION_ID = re.compile(r"^[A-Za-z0-9._-]{1,80}$")
_MAX_CONVERSATION_BYTES = 2 * 1024 * 1024


def _ndjson(event: Dict[str, Any]) -> bytes:
    return (json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def _next_stream_event(iterator):
    try:
        return next(iterator)
    except StopIteration:
        return _STREAM_END


def _close_stream_iterator(iterator) -> None:
    close = getattr(iterator, "close", None)
    if not callable(close):
        return
    try:
        close()
    except Exception:
        log.debug("Provider stream could not be closed cleanly", exc_info=True)


def _gateway_response(result, not_found=False):
    if not result.success:
        err = result.error or ""
        if result.policy_decision:
            status = 403
        elif "not found" in err.lower():
            status = 404
        elif "already exists" in err.lower():
            status = 409
        elif not_found:
            status = 404
        else:
            status = 400
        return JSONResponse({"error": result.error}, status_code=status)
    return None


def _close_stream_after_pending_step(finished, iterator) -> None:
    try:
        finished.result()
    except (asyncio.CancelledError, Exception):
        pass
    _close_stream_iterator(iterator)


def _file_pipeline():
    from modules import get_gateway

    get_orchestrator()
    pipeline = getattr(get_gateway(), "_file_pipeline", None)
    if pipeline is None:
        raise RuntimeError("File pipeline is not configured")
    return pipeline


_require_admin = require_admin_identity


def _scoped_user_id(request: Request, requested_user_id: str = "") -> str:
    identity = request_identity(request)
    if requested_user_id and requested_user_id != identity.user_id and identity.level != "admin":
        raise HTTPException(status_code=403, detail="Cannot access another user's profile")
    return requested_user_id or identity.user_id


def _validate_capabilities(caps: List[str]) -> List[str]:
    invalid: List[str] = []
    cap_reg = get_orchestrator().capability_registry
    if cap_reg is None:
        return invalid
    for cid in caps:
        if cap_reg.get(cid) is None:
            invalid.append(cid)
    return invalid


def get_orchestrator():
    from modules import get_sentinel_orchestrator

    return get_sentinel_orchestrator()


def get_advisory_service():
    orch = get_orchestrator()
    svc = getattr(orch, "_advisory", None)
    return svc


def reset_bridge():
    from modules import reset_sentinel

    reset_sentinel()


def get_goal_registry():
    from modules import get_sentinel_goal_registry

    return get_sentinel_goal_registry()


def get_memory():
    from modules import get_sentinel_memory

    return get_sentinel_memory()


def _memory_record(record) -> Dict[str, Any]:
    outcome = "failed" if record.error or (record.tool_result and record.tool_result.get("success") is False) else "succeeded"
    confidence = 0.95 if record.tool_result and outcome == "succeeded" else 0.85 if record.tool_result else 0.75 if record.error else 0.65
    return {
        "execution_id": record.execution_id,
        "timestamp": record.timestamp,
        "utterance": record.utterance,
        "intent": record.intent,
        "tool_result": record.tool_result,
        "error": record.error,
        "duration_ms": record.duration_ms,
        "session_id": record.context_summary.get("session_id"),
        "memory": {
            "source": "orchestrator.execution",
            "confidence": confidence,
            "outcome": outcome,
            "advisory_only": True,
        },
    }


def _conversation_db():
    from repositories.database import DatabaseManager

    return DatabaseManager()


def _validate_conversation_id(session_id: str) -> str:
    value = str(session_id).strip()
    if not _CONVERSATION_ID.fullmatch(value):
        raise HTTPException(status_code=422, detail="Invalid conversation id")
    return value


def _normalize_conversation_messages(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list) or len(value) > 200:
        raise HTTPException(status_code=422, detail="messages must be a list with at most 200 items")
    allowed = {
        "id", "prompt", "response", "provider", "model", "pipeline",
        "performance", "elapsed", "error", "errorCode", "retryable",
    }
    messages: List[Dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, dict):
            raise HTTPException(status_code=422, detail="Each message must be an object")
        message = {key: raw[key] for key in allowed if key in raw}
        for key in ("id", "prompt", "response", "provider", "model", "error", "errorCode"):
            if key in message and message[key] is not None:
                maximum = 100_000 if key in {"prompt", "response"} else 500
                message[key] = str(message[key])[:maximum]
        if "elapsed" in message and message["elapsed"] is not None:
            try:
                message["elapsed"] = max(0.0, float(message["elapsed"]))
            except (TypeError, ValueError):
                message.pop("elapsed")
        if "retryable" in message:
            message["retryable"] = bool(message["retryable"])
        messages.append(message)
    try:
        encoded = json.dumps(messages, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail="Conversation contains invalid data") from error
    if len(encoded.encode("utf-8")) > _MAX_CONVERSATION_BYTES:
        raise HTTPException(status_code=413, detail="Conversation is too large")
    return messages


def _persist_conversation_turn(
    user_id: str,
    session_id: Optional[str],
    prompt: str,
    response: str,
    *,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    pipeline: Optional[Dict[str, Any]] = None,
    performance: Optional[Dict[str, Any]] = None,
    interrupted: bool = False,
) -> None:
    if not session_id or not response:
        return
    message: Dict[str, Any] = {
        "id": uuid.uuid4().hex,
        "prompt": prompt[:100_000],
        "response": response[:100_000],
        "pipeline": pipeline,
        "performance": performance,
    }
    if provider:
        message["provider"] = provider[:500]
    if model:
        message["model"] = model[:500]
    if interrupted:
        message["error"] = "La respuesta fue interrumpida antes de completarse."
    _conversation_db().append_conversation_message(
        user_id=user_id,
        session_id=session_id,
        title=prompt[:70] or "Nueva operación",
        message=message,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


def _generation_metrics(started_at: float, first_delta_at: Optional[float], text: str) -> Dict[str, Any]:
    from sentinel.core.context_window import count_tokens

    finished_at = time.perf_counter()
    output_tokens = count_tokens(text)
    active_seconds = max(finished_at - (first_delta_at or started_at), 0.001)
    return {
        "time_to_first_token_ms": round(((first_delta_at or finished_at) - started_at) * 1000, 1),
        "generation_ms": round((finished_at - started_at) * 1000, 1),
        "output_tokens": output_tokens,
        "tokens_per_second": round(output_tokens / active_seconds, 2),
    }


def _stream_error_info(error: Exception) -> Dict[str, Any]:
    detail = str(error).lower()
    provider_match = re.search(r"provider\s+([a-z0-9_.-]+)", detail)
    provider = provider_match.group(1) if provider_match else None
    if "unavailable" in detail or "no available" in detail:
        code = "provider_unavailable"
        message = "No hay un proveedor de IA disponible en este momento."
    elif "timeout" in detail or "timed out" in detail:
        code = "provider_timeout"
        message = "El proveedor tardó demasiado en responder."
    elif "connect" in detail or "connection" in detail:
        code = "provider_connection"
        message = "No se pudo conectar con el proveedor de IA."
    elif "interrupted" in detail:
        code = "provider_interrupted"
        message = "El proveedor interrumpió la respuesta antes de terminar."
    else:
        code = "stream_failure"
        message = "La respuesta se interrumpió antes de terminar."
    return {"message": message, "detail": code, "retryable": True, "provider": provider}


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


def get_vault_manager():
    from modules import get_sentinel_vault

    return get_sentinel_vault()


def _build_pipeline_summary(result) -> str:
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


def _format_verified_system_result(target: str, data: Any) -> Optional[str]:
    return _presentation.format_verified_result(target, data)


def _format_governed_outcome(result) -> Optional[str]:
    if not result or result.plan.intent.confidence < 0.6:
        return None
    return _presentation.summary(result)


def _build_chat_pipeline_trace(result) -> Dict[str, Any]:
    plan = result.plan
    step_count = len(plan.plan.steps) if plan.plan and plan.plan.steps else 0
    context_factors = result.decision.context_factors if result.decision else []
    return {
        "presentation": _presentation.present(result, PresentationMode.USER),
        "intent": {
            "action": plan.intent.action,
            "target": plan.intent.target,
            "confidence": plan.intent.confidence,
            "raw_input": plan.intent.raw_input,
        },
        "plan": {
            "steps": step_count,
        },
        "decision": {
            "decision": result.decision.decision if result.decision else None,
            "base_risk_score": result.decision.base_risk_score if result.decision else None,
            "context_modifier": result.decision.context_modifier if result.decision else None,
            "final_risk_score": result.decision.final_risk_score if result.decision else None,
            "reason": result.decision.reason if result.decision else None,
            "context_factors": context_factors,
        }
        if result.decision
        else None,
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
        "execution_id": result.execution_id,
    }


def _get_kb(orch):
    return getattr(orch, "_knowledge_base", None) or getattr(orch._tool_gateway, "_knowledge_base", None)


def _get_pipeline(orch):
    return getattr(orch, "_file_pipeline", None) or getattr(orch._tool_gateway, "_file_pipeline", None)


def _get_web(orch):
    return getattr(orch, "_web_browsing", None) or getattr(orch._tool_gateway, "_web_browsing", None)


def _get_hardening(orch):
    return getattr(orch, "_hardening", None) or getattr(orch._tool_gateway, "_hardening", None)


def _get_profile_mgr():
    try:
        from modules.profile import _svc

        return _svc
    except Exception:
        return None


def _build_pipeline_summary2(result) -> Optional[str]:
    plan = result.plan
    summary_parts = []
    if plan:
        if plan.intent:
            summary_parts.append(f"intent={plan.intent.action}:{plan.intent.target}")
        if plan.plan and plan.plan.steps:
            summary_parts.append(f"steps={len(plan.plan.steps)}")
    decision = result.decision
    if decision:
        summary_parts.append(f"decision={decision.decision} risk={decision.final_risk_score:.2f}")
    return " | ".join(summary_parts) if summary_parts else None
