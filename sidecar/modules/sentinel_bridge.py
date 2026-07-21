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
    """Best-effort release of a provider stream without blocking the event loop."""
    close = getattr(iterator, "close", None)
    if not callable(close):
        return
    try:
        close()
    except Exception:
        # A timed-out ``next`` may still be unwinding in its worker thread. The
        # request must still finish cleanly even if that third-party iterator
        # rejects a concurrent close operation.
        log.debug("Provider stream could not be closed cleanly", exc_info=True)


def _gateway_response(result, not_found=False):
    """Convert a ToolResult to a JSONResponse, mapping policy denials to 403.

    Infers 404/409 from common error patterns when not_found is set.
    """
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
    """Consume an abandoned step result and close its iterator once resumable."""
    try:
        finished.result()
    except (asyncio.CancelledError, Exception):
        # The response already reported its governed timeout/interruption.
        pass
    _close_stream_iterator(iterator)


def _file_pipeline():
    from modules import get_gateway

    get_orchestrator()
    pipeline = getattr(get_gateway(), "_file_pipeline", None)
    if pipeline is None:
        raise RuntimeError("File pipeline is not configured")
    return pipeline


@router.post("/reports/preview")
async def preview_report(body: dict, request: Request):
    return _file_pipeline().preview_report(
        body.get("path", ""),
        recursive=body.get("recursive", True),
        max_files=int(body.get("max_files", 25)),
        expected_output_tokens=int(body.get("expected_output_tokens", 1200)),
    )


@router.post("/reports/export")
async def export_report(body: dict, request: Request):
    content, media_type, filename = _file_pipeline().export_report(
        str(body.get("report", "")),
        str(body.get("format", "markdown")),
    )
    return Response(
        content=content, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


_require_admin = require_admin_identity


def _scoped_user_id(request: Request, requested_user_id: str = "") -> str:
    """Keep profile access owner-scoped unless an administrator explicitly selects a user."""
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


@router.post("/memory/sessions")
async def create_memory_session(body: dict, request: Request):
    return {"session_id": uuid.uuid4().hex[:16], "label": str(body.get("label", ""))[:100]}


@router.get("/conversations")
async def list_conversations(request: Request, limit: int = Query(100, ge=1, le=200)):
    user_id = request_identity(request).user_id
    return {"conversations": _conversation_db().list_conversations(user_id, limit)}


@router.get("/conversations/{session_id}")
async def get_conversation(session_id: str, request: Request):
    user_id = request_identity(request).user_id
    conversation = _conversation_db().get_conversation(
        user_id, _validate_conversation_id(session_id)
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.put("/conversations/{session_id}")
async def save_conversation(session_id: str, body: dict, request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    safe_session_id = _validate_conversation_id(session_id)
    messages = _normalize_conversation_messages(body.get("messages", []))
    title = str(body.get("title", "")).strip()[:120] or "Nueva operación"
    updated_at = datetime.now(timezone.utc).isoformat()
    params = {
        "user_id": identity["user_id"],
        "session_id": safe_session_id,
        "title": title,
        "messages": messages,
        "updated_at": updated_at,
    }
    result = await get_gateway().execute("conversation.save", params, {"identity": identity})
    resp = _gateway_response(result)
    if resp:
        return resp
    return result.data


@router.delete("/conversations/{session_id}")
async def delete_conversation(session_id: str, request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    safe_session_id = _validate_conversation_id(session_id)
    params = {"user_id": identity["user_id"], "session_id": safe_session_id}
    result = await get_gateway().execute("conversation.delete", params, {"identity": identity})
    resp = _gateway_response(result, not_found=True)
    if resp:
        return resp
    return result.data


@router.get("/memory/sessions")
async def list_memory_sessions(request: Request, limit: int = Query(50, ge=1, le=200)):
    from modules.auth import request_identity

    identity = request_identity(request).to_dict()
    memory = get_memory() or get_orchestrator()._memory
    return {"sessions": memory.list_sessions(identity["user_id"], limit=limit)}


@router.get("/memory/sessions/{session_id}")
async def get_memory_session(session_id: str, request: Request, limit: int = Query(100, ge=1, le=200)):
    from modules.auth import request_identity

    identity = request_identity(request).to_dict()
    memory = get_memory() or get_orchestrator()._memory
    records = memory.get_session_history(session_id, limit=limit, user_id=identity["user_id"])
    if not records:
        return JSONResponse(status_code=404, content={"error": "Session not found"})
    return {"session_id": session_id, "records": [_memory_record(record) for record in reversed(records)]}


@router.get("/memory/search")
async def search_memory(request: Request, q: str = Query("", min_length=1), limit: int = Query(50, ge=1, le=200)):
    from modules.auth import request_identity

    identity = request_identity(request).to_dict()
    memory = get_memory() or get_orchestrator()._memory
    return {"results": [_memory_record(record) for record in memory.search_memory(identity["user_id"], q, limit)]}


@router.delete("/memory/sessions/{session_id}")
async def delete_memory_session(session_id: str, request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    params = {"session_id": session_id, "user_id": identity["user_id"]}
    result = await get_gateway().execute("memory.session.delete", params, {"identity": identity})
    resp = _gateway_response(result, not_found=True)
    if resp:
        return resp
    return result.data


@router.get("/memory/environment")
async def list_environment_memory(request: Request, limit: int = Query(50, ge=1, le=200)):
    """Expose only the current user's privacy-safe environmental observations."""
    identity = request_identity(request)
    memory = get_memory() or get_orchestrator()._memory
    changes = memory.get_environment_changes(identity.user_id, limit=limit)
    return {
        "changes": [asdict(change) for change in changes],
        "advisory_only": True,
        "privacy": "No activity, file content, browser history, executable paths or secrets are stored.",
    }


@router.delete("/memory/environment")
async def delete_environment_memory(request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    params = {"user_id": identity["user_id"]}
    result = await get_gateway().execute("memory.environment.delete", params, {"identity": identity})
    resp = _gateway_response(result)
    if resp:
        return resp
    return result.data


@router.get("/permissions/rules")
async def list_granular_permission_rules(request: Request):
    from modules.permissions import _svc

    return {"rules": _svc.list_rules()}


@router.post("/permissions/rules")
async def add_granular_permission_rule(body: dict, request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    result = await get_gateway().execute("permissions.add_rule", body, {"identity": identity})
    resp = _gateway_response(result)
    if resp:
        return resp
    return result.data


@router.delete("/permissions/rules/{rule_id}")
async def delete_granular_permission_rule(rule_id: str, request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    result = await get_gateway().execute("permissions.remove_rule", {"rule_id": rule_id}, {"identity": identity})
    resp = _gateway_response(result, not_found=True)
    if resp:
        return resp
    return result.data


@router.post("/process")
async def process_utterance(body: dict, request: Request):
    from modules.auth import request_identity

    orch = get_orchestrator()
    utterance = body.get("utterance", "")
    if not utterance:
        return {"error": "utterance is required"}
    raw_session_id = body.get("session_id")
    session_id = _validate_conversation_id(raw_session_id) if raw_session_id else None
    dry_run = body.get("dry_run", False)
    presentation_mode = PresentationMode.parse(body.get("presentation_mode"))
    result = await orch.process(
        utterance,
        identity=request_identity(request).to_dict(),
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

    return {
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


def get_vault_manager():
    from modules import get_sentinel_vault

    return get_sentinel_vault()


@router.post("/process/multi-agent")
async def process_multi_agent(body: dict, request: Request):
    from modules.auth import request_identity

    orch = get_orchestrator()
    utterance = body.get("utterance", "")
    if not utterance:
        return {"error": "utterance is required"}
    session_id = body.get("session_id")
    result = await orch.process_multi_agent(
        utterance,
        identity=request_identity(request).to_dict(),
        session_id=session_id,
    )
    return {
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


# ── Vault endpoints ──────────────────────────────────────────
@router.get("/vault/entries")
async def vault_list(request: Request, category: str = ""):
    _require_admin(request)
    vault = get_vault_manager()
    entries = vault.list_entries(category)
    return {"entries": [e.to_dict() for e in entries], "total": len(entries)}


@router.get("/vault/entries/{vault_id}")
async def vault_get(vault_id: str, request: Request):
    _require_admin(request)
    vault = get_vault_manager()
    entry = vault.get_entry(vault_id)
    if not entry:
        return {"error": "not found"}, 404
    return {"entry": entry.to_dict()}


@router.post("/vault/entries")
async def vault_create(body: dict, request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    result = await get_gateway().execute("vault.create", body, {"identity": identity})
    resp = _gateway_response(result)
    if resp:
        return resp
    return result.data


@router.patch("/vault/entries/{vault_id}")
async def vault_update(vault_id: str, body: dict, request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    params = {"vault_id": vault_id, **body}
    result = await get_gateway().execute("vault.update", params, {"identity": identity})
    resp = _gateway_response(result)
    if resp:
        return resp
    return result.data


@router.delete("/vault/entries/{vault_id}")
async def vault_delete(vault_id: str, request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    result = await get_gateway().execute("vault.delete", {"vault_id": vault_id}, {"identity": identity})
    resp = _gateway_response(result, not_found=True)
    if resp:
        return resp
    return result.data


@router.post("/vault/entries/{vault_id}/reveal")
async def vault_reveal(vault_id: str, request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    result = await get_gateway().execute("vault.reveal", {"vault_id": vault_id}, {"identity": identity})
    resp = _gateway_response(result, not_found=True)
    if resp:
        return resp
    return result.data


@router.post("/vault/entries/{vault_id}/rotate")
async def vault_rotate_secret(vault_id: str, request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    result = await get_gateway().execute("vault.rotate_secret", {"vault_id": vault_id}, {"identity": identity})
    resp = _gateway_response(result, not_found=True)
    if resp:
        return resp
    return result.data


@router.post("/vault/rotate-master-key")
async def vault_rotate_master(request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    result = await get_gateway().execute("vault.rotate_master_key", {}, {"identity": identity})
    resp = _gateway_response(result)
    if resp:
        return resp
    return result.data


@router.get("/vault/audit")
async def vault_audit(request: Request, vault_id: str = "", limit: int = 50):
    _require_admin(request)
    vault = get_vault_manager()
    entries = vault.get_audit_log(vault_id, limit)
    return {"audit": [e.__dict__ for e in entries]}


@router.get("/vault/status")
async def vault_status(request: Request):
    _require_admin(request)
    vault = get_vault_manager()
    entries = vault.list_entries()
    has_fernet = vault._fernet is not None
    return {
        "entry_count": len(entries),
        "encryption_enabled": has_fernet,
        "categories": list({e.category for e in entries}),
    }


def _build_pipeline_summary(result) -> str:
    plan = result.plan
    intent = plan.intent
    decision = result.decision
    tool_result = result.tool_result
    parts = [
        f"Intent: {intent.action} → {intent.target} (confidence={intent.confidence:.2f})",
    ]
    if decision:
        parts.append(f"Decision: {decision.decision} (risk={decision.final_risk_score:.2f}, reason={decision.reason})")
    if tool_result:
        status = "success" if tool_result.success else f"error: {tool_result.error}"
        parts.append(f"Tool: {tool_result.tool_id} → {status}")
    return " | ".join(parts)


def _format_verified_system_result(target: str, data: Any) -> Optional[str]:
    return _presentation.format_verified_result(target, data)


def _format_governed_outcome(result) -> Optional[str]:
    """Describe an executable turn from trusted pipeline state only.

    Model-generated prose must never be allowed to turn a rejection, pending
    confirmation, or tool failure into a success claim.
    """
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


@router.post("/advisory/feedback")
async def advisory_feedback(body: dict, request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    result = await get_gateway().execute("advisory.feedback", body, {"identity": identity})
    resp = _gateway_response(result)
    if resp:
        return resp
    return result.data


@router.post("/chat")
async def sentinel_chat(body: dict, request: Request):
    from modules.auth import request_identity
    from modules.ai_provider import _svc as ai_svc

    orch = get_orchestrator()
    identity = request_identity(request).to_dict()
    message = body.get("message", "")
    history = body.get("context", [])
    raw_session_id = body.get("session_id")
    session_id = _validate_conversation_id(raw_session_id) if raw_session_id else None

    if not message:
        return {
            "response": "Please provide a message.",
            "provider": None,
            "model": None,
            "pipeline": None,
            "conversation_mode": "core",
            "capabilities": ai_svc.conversation_capabilities(),
        }

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
    try:
        # Planning enriches conversation, but it must never hold the chat open.
        # A timed-out planner is discarded and the always-available conversation
        # layer still answers the user.
        if requires_pipeline:
            result = await asyncio.wait_for(
                orch.process(message, identity=identity, session_id=session_id),
                timeout=15,
            )
            intent = result.plan.intent
            pipeline_summary = _build_pipeline_summary(result)
            pipeline_trace = _build_chat_pipeline_trace(result)
            actionable = intent.confidence >= 0.6
    except Exception:
        log.exception("Orchestration unavailable; conversation continuity remains active")

    # Educational and code answers can exceed the short-answer budget. The
    # provider retains its own timeout, so the request remains bounded.
    _AI_TIMEOUT = 48

    conversation_mode = "core"
    conversation_capabilities = ai_svc.conversation_capabilities()

    if actionable and result:
        governed_response = _format_governed_outcome(result)
        if governed_response:
            try:
                await asyncio.to_thread(
                    _persist_conversation_turn,
                    identity["user_id"],
                    session_id,
                    message,
                    governed_response,
                    provider="sentinel_core",
                    pipeline=pipeline_trace,
                )
            except Exception:
                log.exception("Could not persist conversation turn")
            return {
                "response": governed_response,
                "provider": "sentinel_core",
                "model": None,
                "pipeline": pipeline_trace,
                "conversation_mode": "core",
                "capabilities": conversation_capabilities,
            }
        tool_data = result.tool_result.data if result.tool_result else None
        try:
            ctx = list(history) if history else []
            if ctx:
                ctx.append({"role": "system", "content": f"Pipeline analysis:\n{pipeline_summary}"})
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
            conversation_mode = fmt_response.get("conversation_mode", conversation_mode)
            conversation_capabilities = fmt_response.get("capabilities", conversation_capabilities)
        except asyncio.TimeoutError:
            log.warning("Advanced result formatting timed out; using core conversation")
            core = ai_svc._conversation.respond(
                ConversationRequest(message=message, purpose="tool_result", tool_result=tool_data)
            ).to_dict()
            response_text, provider, model = core["response"], None, None
            conversation_mode, conversation_capabilities = core["conversation_mode"], core["capabilities"]
        except Exception:
            log.exception("Result formatting failed; using core conversation")
            core = ai_svc._conversation.respond(
                ConversationRequest(message=message, purpose="tool_result", tool_result=tool_data)
            ).to_dict()
            response_text, provider, model = core["response"], None, None
            conversation_mode, conversation_capabilities = core["conversation_mode"], core["capabilities"]
    else:
        try:
            ctx = list(history) if history else []
            enrich_ctx = list(ctx)
            enrich_ctx.append({"role": "system", "content": f"Sentinel pipeline context:\n{pipeline_summary}"})
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
        except asyncio.TimeoutError:
            log.warning("Advanced chat timed out; using core conversation")
            core = ai_svc._conversation.respond(ConversationRequest(message=message, context=ctx)).to_dict()
            response_text, provider, model = core["response"], None, None
            conversation_mode, conversation_capabilities = core["conversation_mode"], core["capabilities"]
        except Exception:
            log.exception("Chat integration failed; using core conversation")
            core = ai_svc._conversation.respond(ConversationRequest(message=message, context=ctx)).to_dict()
            response_text, provider, model = core["response"], None, None
            conversation_mode, conversation_capabilities = core["conversation_mode"], core["capabilities"]

    try:
        await asyncio.to_thread(
            _persist_conversation_turn,
            identity["user_id"],
            session_id,
            message,
            response_text,
            provider=provider,
            model=model,
            pipeline=pipeline_trace,
        )
    except Exception:
        log.exception("Could not persist conversation turn")
    return {
        "response": response_text,
        "provider": provider,
        "model": model,
        "pipeline": pipeline_trace,
        "conversation_mode": conversation_mode,
        "capabilities": conversation_capabilities,
    }


@router.post("/chat/stream")
async def sentinel_chat_stream(body: dict, request: Request):
    """Stream a governed conversation as newline-delimited JSON events."""
    from modules.ai_provider import _svc as ai_svc

    message = str(body.get("message", "")).strip()
    history = body.get("context", [])
    raw_session_id = body.get("session_id")
    session_id = _validate_conversation_id(raw_session_id) if raw_session_id else None
    identity = request_identity(request).to_dict()

    async def events():
        if not message:
            yield _ndjson({"type": "error", "message": "Please provide a message."})
            return

        yield _ndjson({"type": "status", "stage": "planning"})
        turn_started = time.perf_counter()
        response_parts: List[str] = []
        response_provider: Optional[str] = None
        response_model: Optional[str] = None
        performance_metrics: Optional[Dict[str, Any]] = None
        persisted = False

        async def persist(interrupted: bool = False) -> None:
            nonlocal persisted
            if persisted or not response_parts:
                return
            try:
                await asyncio.to_thread(
                    _persist_conversation_turn,
                    identity["user_id"],
                    session_id,
                    message,
                    "".join(response_parts),
                    provider=response_provider,
                    model=response_model,
                    pipeline=pipeline_trace,
                    performance=performance_metrics,
                    interrupted=interrupted,
                )
                persisted = True
            except Exception:
                log.exception("Could not persist conversation turn")

        result = None
        pipeline_trace = None
        pipeline_summary = "No orchestration context is available for this turn."
        orchestrator = get_orchestrator()
        preflight_intent = orchestrator.classify_intent(message)
        requires_pipeline = preflight_intent.confidence >= 0.6
        if requires_pipeline:
            try:
                result = await asyncio.wait_for(
                    orchestrator.process(message, identity=identity, session_id=session_id),
                    timeout=15,
                )
                pipeline_trace = _build_chat_pipeline_trace(result)
                pipeline_summary = _build_pipeline_summary(result)
            except Exception:
                log.exception("Streaming orchestration unavailable; conversation remains active")
        else:
            pipeline_summary = (
                "Conversation-only route selected: no executable system intent was detected, "
                "so no tool was planned or authorized."
            )

        yield _ndjson(
            {
                "type": "pipeline",
                "pipeline": pipeline_trace,
                "stage": "generating",
                "planning_ms": round((time.perf_counter() - turn_started) * 1000, 1),
                "route": "governed" if requires_pipeline else "conversation",
            }
        )
        generation_started = time.perf_counter()
        first_delta_at: Optional[float] = None

        actionable = bool(result and result.plan.intent.confidence >= 0.6)
        if actionable and result:
            verified = _format_governed_outcome(result)
            if verified:
                yield _ndjson(
                    {"type": "meta", "provider": "sentinel_core", "model": None}
                )
                yield _ndjson({"type": "delta", "text": verified})
                response_parts.append(verified)
                response_provider = "sentinel_core"
                first_delta_at = time.perf_counter()
                performance_metrics = _generation_metrics(
                    generation_started, first_delta_at, verified
                )
                await persist()
                yield _ndjson({"type": "metrics", **performance_metrics})
                yield _ndjson({"type": "done"})
                return

        enriched_context = list(history) if isinstance(history, list) else []
        enriched_context.append(
            {"role": "system", "content": f"Sentinel pipeline context:\n{pipeline_summary}"}
        )
        iterator = ai_svc.stream_chat(
            message=message,
            context=enriched_context,
            system_prompt=(
                "You are Sentinel, the local trust and orchestration layer between the user, "
                "AI models, tools, and the operating system. Explain decisions accurately and "
                "never claim an action occurred unless the supplied pipeline confirms it."
            ),
        )
        pending_next = None
        try:
            while not await request.is_disconnected():
                pending_next = asyncio.create_task(
                    asyncio.to_thread(_next_stream_event, iterator)
                )
                event = await asyncio.wait_for(
                    asyncio.shield(pending_next),
                    timeout=_STREAM_IDLE_TIMEOUT_SECONDS,
                )
                pending_next = None
                if event is _STREAM_END:
                    await persist(interrupted=True)
                    return
                if event.get("type") == "meta":
                    response_provider = event.get("provider")
                    response_model = event.get("model")
                elif event.get("type") == "delta":
                    if first_delta_at is None:
                        first_delta_at = time.perf_counter()
                    response_parts.append(str(event.get("text", "")))
                elif event.get("type") == "done":
                    performance_metrics = _generation_metrics(
                        generation_started, first_delta_at, "".join(response_parts)
                    )
                    await persist()
                    yield _ndjson({"type": "metrics", **performance_metrics})
                yield _ndjson(event)
            await persist(interrupted=True)
        except asyncio.TimeoutError:
            log.warning("Conversation stream exceeded the inactivity timeout")
            await persist(interrupted=True)
            yield _ndjson(
                {
                    "type": "error",
                    "message": "El modelo dejó de responder. Intenta nuevamente.",
                    "detail": "stream_idle_timeout",
                    "retryable": True,
                    "provider": response_provider,
                }
            )
        except Exception as error:
            log.exception("Conversation stream failed")
            await persist(interrupted=True)
            yield _ndjson({"type": "error", **_stream_error_info(error)})
        finally:
            if pending_next is not None and not pending_next.done():
                # ``asyncio.to_thread`` cannot interrupt a synchronous ``next``.
                # Close again as soon as that in-flight call releases the
                # generator so a timeout or disconnect cannot strand it.
                pending_next.add_done_callback(
                    lambda finished: _close_stream_after_pending_step(
                        finished, iterator
                    )
                )
            await asyncio.to_thread(_close_stream_iterator, iterator)

    return StreamingResponse(
        events(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/capabilities")
def get_capabilities():
    orch = get_orchestrator()
    return orch.get_capabilities()


@router.get("/conversation/capabilities")
def get_conversation_capabilities():
    from modules.ai_provider import _svc as ai_svc

    get_orchestrator()
    return ai_svc.conversation_capabilities()


@router.get("/goals")
def get_goals():
    goal_registry = get_goal_registry()
    if goal_registry is None:
        return {"goals": []}
    return {"goals": [g.to_dict() for g in goal_registry.list_all()]}


@router.post("/goals")
async def post_goal(body: dict, request: Request):
    from modules import get_gateway
    from sentinel.core.goals import GoalDefinition, RiskLevel

    identity = request_identity(request).to_dict()
    gid = body.get("id")
    if not gid:
        return JSONResponse({"error": "id is required"}, status_code=400)
    priority = body.get("priority", 0)
    if not (0 <= priority <= 10):
        return JSONResponse({"error": "priority must be 0-10"}, status_code=400)
    intent_targets = body.get("intent_targets", [])
    if not intent_targets:
        return JSONResponse({"error": "intent_targets must not be empty"}, status_code=400)
    caps = body.get("possible_capabilities", [])
    goal_registry = get_goal_registry()
    if goal_registry is not None and caps and not goal_registry._test_skip_cap_validation:
        invalid = _validate_capabilities(caps)
        if invalid:
            return JSONResponse({"error": f"unknown capabilities: {invalid}"}, status_code=400)
    risk_str = body.get("base_risk", "low")
    if risk_str not in ("low", "medium", "high", "critical"):
        return JSONResponse({"error": f"invalid base_risk: {risk_str}"}, status_code=400)
    if goal_registry is not None and goal_registry.get(gid) is not None:
        return JSONResponse({"error": f"goal '{gid}' already exists"}, status_code=409)
    result = await get_gateway().execute("goals.register", body, {"identity": identity})
    resp = _gateway_response(result)
    if resp:
        return resp
    return JSONResponse(result.data, status_code=201)


@router.delete("/goals/{goal_id}")
async def delete_goal(goal_id: str, request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    result = await get_gateway().execute("goals.unregister", {"goal_id": goal_id}, {"identity": identity})
    resp = _gateway_response(result, not_found=True)
    if resp:
        return resp
    return result.data


@router.patch("/goals/{goal_id}")
async def patch_goal(goal_id: str, body: dict, request: Request):
    from modules import get_gateway
    from sentinel.core.goals import RiskLevel

    identity = request_identity(request).to_dict()
    goal_registry = get_goal_registry()
    if goal_registry is None:
        get_orchestrator()
        goal_registry = get_goal_registry()
    if goal_registry is None or goal_registry.get(goal_id) is None:
        return JSONResponse({"error": f"goal '{goal_id}' not found"}, status_code=404)
    clen = body.get("priority")
    if clen is not None and not (0 <= clen <= 10):
        return JSONResponse({"error": "priority must be 0-10"}, status_code=400)
    params = {"goal_id": goal_id}
    allowed = {
        "name", "description", "related_intents", "possible_capabilities",
        "priority", "base_risk", "keywords", "enabled", "context_rules",
    }
    for k, v in body.items():
        if k in allowed and v is not None:
            params[k] = v
    if len(params) == 1:
        return JSONResponse({"error": "no valid fields to update"}, status_code=400)
    if "possible_capabilities" in params and not goal_registry._test_skip_cap_validation:
        invalid = _validate_capabilities(params["possible_capabilities"])
        if invalid:
            return JSONResponse({"error": f"unknown capabilities: {invalid}"}, status_code=400)
    if "base_risk" in params:
        rv = params["base_risk"]
        if rv not in ("low", "medium", "high", "critical"):
            return JSONResponse({"error": f"invalid base_risk: {rv}"}, status_code=400)
    result = await get_gateway().execute("goals.update", params, {"identity": identity})
    resp = _gateway_response(result, not_found=True)
    if resp:
        return resp
    return result.data


@router.get("/goals/audit")
def get_goal_audit(request: Request):
    _require_admin(request)
    goal_registry = get_goal_registry()
    if goal_registry is None:
        get_orchestrator()
        goal_registry = get_goal_registry()
    return {
        "audit_log": [
            {
                "timestamp": e.timestamp,
                "operation": e.operation,
                "goal_id": e.goal_id,
                "source": e.source,
                "details": e.details,
            }
            for e in goal_registry.get_audit_log()
        ]
    }


@router.get("/goals/matches")
def get_goal_matches(
    intent: str = Query(..., description="Intent target to match against goals"),
    cpu: Optional[float] = Query(None, description="cpu_percent context override"),
    memory: Optional[float] = Query(None, description="memory_percent context override"),
    disk: Optional[float] = Query(None, description="disk_percent context override"),
    verbose: Optional[bool] = Query(False, description="Include score breakdown"),
):
    from sentinel.core.goals import GoalScorer

    goal_registry = get_goal_registry()
    if goal_registry is None:
        get_orchestrator()
        goal_registry = get_goal_registry()
    context = {}
    if cpu is not None:
        context["cpu_percent"] = cpu
    if memory is not None:
        context["memory_percent"] = memory
    if disk is not None:
        context["disk_percent"] = disk
    candidates = goal_registry.find_candidates(intent)
    scorer = GoalScorer(context)
    ranked = scorer.rank(candidates)
    matches = []
    for s in ranked:
        entry = {
            "goal": s.result.goal.id,
            "goal_name": s.result.goal.name,
            "score": s.score,
            "confidence": s.result.confidence,
            "match_type": s.result.match_type,
            "matched_by": s.result.matched_by,
            "reasons": s.reasons,
        }
        if verbose:
            cfg = scorer.get_config()
            cw = cfg.confidence_weight
            pw = cfg.priority_weight
            ctw = cfg.context_weight
            entry["breakdown"] = {
                "confidence_score": round(s.result.confidence * cw, 4),
                "priority_score": round((s.result.goal.priority / 10.0) * pw, 4),
                "context_score": round(scorer._context_bonus(s.result.goal) * ctw, 4),
            }
        matches.append(entry)
    return {
        "intent": intent,
        "context": context,
        "matches": matches,
    }


@router.post("/simulate/approve")
async def approve_execution(body: dict, request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    action_id = body.get("action_id", "")
    if not action_id:
        return JSONResponse({"error": "action_id is required"}, status_code=400)
    result = await get_gateway().execute("simulate.approve", body, {"identity": identity})
    resp = _gateway_response(result)
    if resp:
        return resp
    return result.data


@router.post("/simulate/modify-and-approve")
async def modify_and_approve(body: dict, request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    action_id = body.get("action_id", "")
    if not action_id:
        return JSONResponse({"error": "action_id is required"}, status_code=400)
    steps = body.get("steps", [])
    if not steps:
        return JSONResponse({"error": "steps are required"}, status_code=400)
    params = {"action_id": action_id, "steps": steps}
    result = await get_gateway().execute("simulate.modify_and_approve", params, {"identity": identity})
    resp = _gateway_response(result)
    if resp:
        return resp
    return {
        **result.data,
        "modified": True,
        "requires_reconfirmation": result.data.get("blocked", False) and bool(result.data.get("action_id")),
    }


@router.post("/simulate/reject")
async def reject_execution(body: dict, request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    action_id = body.get("action_id", "")
    if not action_id:
        return JSONResponse({"error": "action_id is required"}, status_code=400)
    params = {"action_id": action_id, "approved": False}
    result = await get_gateway().execute("simulate.approve", params, {"identity": identity})
    resp = _gateway_response(result)
    if resp:
        return resp
    return result.data


@router.get("/feedback/stats")
def get_feedback_stats(
    provider_id: Optional[str] = Query(None),
    task_type: Optional[str] = Query(None),
):
    orch = get_orchestrator()
    store = orch.feedback_store
    if store is None:
        return {"stats": []}
    tt = None
    if task_type:
        from sentinel.core.model_router import TaskType

        try:
            tt = TaskType(task_type)
        except ValueError:
            return JSONResponse({"error": f"Invalid task_type: {task_type}"}, status_code=400)
    stats = store.get_stats(provider_id=provider_id, task_type=tt)
    return {
        "stats": [
            {
                "provider_id": s.provider_id,
                "task_type": s.task_type.value,
                "total": s.total,
                "successes": s.successes,
                "failures": s.failures,
                "avg_duration_ms": s.avg_duration_ms,
                "success_rate": s.success_rate,
            }
            for s in stats
        ]
    }


@router.get("/feedback/records")
def get_feedback_records(
    provider_id: Optional[str] = Query(None),
    task_type: Optional[str] = Query(None),
    limit: int = Query(100),
):
    orch = get_orchestrator()
    store = orch.feedback_store
    if store is None:
        return {"records": []}
    tt = None
    if task_type:
        from sentinel.core.model_router import TaskType

        try:
            tt = TaskType(task_type)
        except ValueError:
            return JSONResponse({"error": f"Invalid task_type: {task_type}"}, status_code=400)
    records = store._records
    if provider_id:
        records = [r for r in records if r.provider_id == provider_id]
    if tt:
        records = [r for r in records if r.task_type == tt]
    return {
        "records": [
            {
                "provider_id": r.provider_id,
                "model": r.model,
                "task_type": r.task_type.value,
                "success": r.success,
                "duration_ms": r.duration_ms,
                "timestamp": r.timestamp,
                "error": r.error,
            }
            for r in records[-limit:]
        ]
    }


@router.get("/cost/summary")
def get_cost_summary(
    provider_id: Optional[str] = Query(None),
    since: Optional[str] = Query(None),
):
    orch = get_orchestrator()
    ct = orch.cost_tracker
    if ct is None:
        return {"summary": []}
    summaries = ct.get_cost_summary(provider_id=provider_id, since=since)
    return {
        "summary": [
            {
                "provider_id": s.provider_id,
                "model": s.model,
                "total_calls": s.total_calls,
                "total_prompt_tokens": s.total_prompt_tokens,
                "total_completion_tokens": s.total_completion_tokens,
                "total_tokens": s.total_tokens,
                "total_cost_usd": s.total_cost_usd,
            }
            for s in summaries
        ]
    }


@router.get("/cost/total")
def get_total_cost(
    provider_id: Optional[str] = Query(None),
    since: Optional[str] = Query(None),
):
    orch = get_orchestrator()
    ct = orch.cost_tracker
    if ct is None:
        return {"total_cost_usd": 0.0, "total_tokens": 0}
    return {
        "total_cost_usd": ct.get_total_cost(provider_id=provider_id, since=since),
        "total_tokens": ct.get_total_tokens(provider_id=provider_id, since=since),
    }


@router.get("/cost/budgets")
def get_budgets():
    orch = get_orchestrator()
    ct = orch.cost_tracker
    if ct is None:
        return {"budgets": []}
    return {
        "budgets": [
            {
                "name": b.name,
                "max_cost_usd": b.max_cost_usd,
                "period": b.period,
                "provider_id": b.provider_id,
                "max_tokens": b.max_tokens,
                "enabled": b.enabled,
            }
            for b in ct.get_budgets()
        ]
    }


@router.post("/cost/budgets")
async def create_budget(body: dict, request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    name = body.get("name", "")
    if not name:
        return JSONResponse({"error": "name is required"}, status_code=400)
    result = await get_gateway().execute("budget.create", body, {"identity": identity})
    resp = _gateway_response(result)
    if resp:
        return resp
    return result.data


@router.delete("/cost/budgets/{name}")
async def delete_budget(name: str, request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    result = await get_gateway().execute("budget.delete", {"name": name}, {"identity": identity})
    resp = _gateway_response(result)
    if resp:
        return resp
    return result.data


@router.get("/cost/alerts")
def get_cost_alerts():
    orch = get_orchestrator()
    ct = orch.cost_tracker
    if ct is None:
        return {"alerts": []}
    return {
        "alerts": [
            {
                "budget_name": a.budget_name,
                "provider_id": a.provider_id,
                "current_cost": a.current_cost,
                "max_cost": a.max_cost,
                "current_tokens": a.current_tokens,
                "max_tokens": a.max_tokens,
                "period": a.period,
            }
            for a in ct.check_budgets()
        ]
    }


@router.get("/performance/baselines")
def get_performance_baselines():
    orch = get_orchestrator()
    pt = orch.performance_tracker
    if pt is None:
        return {"baselines": []}
    return {
        "baselines": [
            {
                "provider_id": b.provider_id,
                "model": b.model,
                "task_type": b.task_type.value,
                "tool_id": b.tool_id,
                "avg_duration_ms": b.avg_duration_ms,
                "std_duration_ms": b.std_duration_ms,
                "sample_count": b.sample_count,
                "min_duration_ms": b.min_duration_ms,
                "max_duration_ms": b.max_duration_ms,
            }
            for b in pt.get_baselines()
        ]
    }


@router.get("/performance/alerts")
def get_performance_alerts(severity: Optional[str] = Query(None)):
    orch = get_orchestrator()
    pt = orch.performance_tracker
    if pt is None:
        return {"alerts": []}
    return {
        "alerts": [
            {
                "provider_id": a.provider_id,
                "model": a.model,
                "task_type": a.task_type.value,
                "tool_id": a.tool_id,
                "baseline_avg": a.baseline_avg,
                "current_avg": a.current_avg,
                "deviation_pct": a.deviation_pct,
                "severity": a.severity,
                "timestamp": a.timestamp,
            }
            for a in pt.get_alerts(severity=severity)
        ]
    }


@router.get("/cache/stats")
def get_cache_stats():
    orch = get_orchestrator()
    pc = orch.plan_cache
    if pc is None:
        return {"enabled": False}
    return {"enabled": True, **pc.stats()}


@router.post("/cache/clear")
async def clear_cache(request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    result = await get_gateway().execute("cache.clear", {}, {"identity": identity})
    resp = _gateway_response(result)
    if resp:
        return resp
    return result.data


@router.get("/circuit-breaker")
def get_circuit_breaker_states():
    orch = get_orchestrator()
    result = {"model_circuits": [], "tool_circuits": []}
    if orch._model_router:
        result["model_circuits"] = [
            {**state, "resource_type": "model", "resource_id": state["provider_id"]}
            for state in orch._model_router.circuit_breaker.get_all_states()
        ]
    h = _get_hardening(orch)
    if h is not None:
        result["tool_circuits"] = [
            {**state, "resource_type": "tool", "resource_id": state["provider_id"]}
            for state in h.circuit_breaker.get_all_states()
        ]
    # Backward-compatible aggregate used by the desktop observability client.
    # Keep the typed collections above so callers can still distinguish models
    # from tools without guessing from an identifier.
    result["circuits"] = result["model_circuits"] + result["tool_circuits"]
    return result


@router.get("/recovery/status")
def get_recovery_status():
    """Unified, non-secret recovery diagnostics for desktop observability."""
    orch = get_orchestrator()
    circuits = get_circuit_breaker_states()
    hardening = _get_hardening(orch)
    model_router = getattr(orch, "_model_router", None)
    return {
        "enabled": True,
        **circuits,
        "tool_recovery": hardening.stats() if hardening is not None else {"enabled": False},
        "model_fallback": model_router.fallback_stats() if model_router is not None else {"enabled": False},
    }


@router.get("/integrations/status")
def get_integrations_status():
    orch = get_orchestrator()
    service = getattr(orch._tool_gateway, "_desktop_integrations", None)
    if service is None:
        return {"enabled": False, "integrations": {}}
    return {"enabled": True, "integrations": service.status()}


@router.get("/observability/overview")
def get_observability_overview():
    orch = get_orchestrator()
    service = getattr(orch._tool_gateway, "_observability", None)
    trace_summary = service.summary() if service is not None else {}
    cost_tracker = getattr(orch, "_cost_tracker", None)
    cost_rows = cost_tracker.get_cost_summary() if cost_tracker is not None else []
    performance = getattr(orch, "_perf_tracker", None)
    baselines = performance.get_baselines() if performance is not None else []
    alert_manager = getattr(orch, "_alert_manager", None)
    return {
        "enabled": service is not None,
        "traces": trace_summary,
        "costs": {
            "total_cost_usd": round(sum(row.total_cost_usd for row in cost_rows), 6),
            "total_tokens": sum(row.total_tokens for row in cost_rows),
            "total_calls": sum(row.total_calls for row in cost_rows),
            "by_model": [asdict(row) for row in cost_rows],
        },
        "latency_baselines": [{**asdict(row), "task_type": row.task_type.value} for row in baselines[:50]],
        "alerts": alert_manager.stats()
        if alert_manager is not None
        else {"total": 0, "unacknowledged": 0, "by_source": {}},
    }


@router.get("/observability/traces")
def get_observability_traces(
    limit: int = Query(100, ge=1, le=500),
    tool_id: Optional[str] = Query(None),
):
    orch = get_orchestrator()
    service = getattr(orch._tool_gateway, "_observability", None)
    if service is None:
        return {"traces": [], "summary": {}}
    return {"traces": service.traces(limit=limit, tool_id=tool_id), "summary": service.summary()}


@router.get("/observability/pipeline-metrics")
def get_pipeline_metrics():
    from modules import get_pipeline_metrics as _get_pm
    svc = _get_pm()
    return {
        "summary": svc.summary(),
        "component_durations": svc.component_durations(),
        "tool_usage": svc.tool_usage(),
        "throughput": svc.throughput(),
        "bottlenecks": svc.bottlenecks(),
    }


@router.get("/observability/component-durations")
def get_component_durations(limit: int = Query(50, ge=1, le=200)):
    from modules import get_pipeline_metrics as _get_pm
    return {"components": _get_pm().component_durations(limit=limit)}


@router.get("/observability/tool-usage")
def get_tool_usage(limit: int = Query(10, ge=1, le=50)):
    from modules import get_pipeline_metrics as _get_pm
    return {"tools": _get_pm().tool_usage(limit=limit)}


@router.get("/observability/throughput")
def get_throughput():
    from modules import get_pipeline_metrics as _get_pm
    return _get_pm().throughput()


@router.get("/observability/bottlenecks")
def get_bottlenecks(limit: int = Query(5, ge=1, le=20)):
    from modules import get_pipeline_metrics as _get_pm
    return {"bottlenecks": _get_pm().bottlenecks(limit=limit)}


@router.get("/observability/timeline/{request_id}")
def get_timeline(request_id: str):
    from modules import get_pipeline_metrics as _get_pm
    return _get_pm().timeline(request_id)


@router.post("/recovery/circuit-breaker/reset")
async def reset_recovery_circuit(body: dict, request: Request):
    from modules import get_gateway

    resource_type = str(body.get("resource_type", "")).strip().lower()
    resource_id = str(body.get("resource_id", "")).strip()
    if resource_type not in ("model", "tool") or not resource_id:
        raise HTTPException(status_code=400, detail="resource_type (model|tool) and resource_id are required")
    identity = request_identity(request).to_dict()
    result = await get_gateway().execute("circuit_breaker.reset_tool", body, {"identity": identity})
    resp = _gateway_response(result)
    if resp:
        return resp
    return result.data


@router.get("/model-router/status")
def get_model_router_status(refresh: bool = Query(False)):
    """Expose routing readiness without leaking API keys."""
    from sentinel.core.hardware_intelligence import get_hardware_profiler

    router = get_orchestrator()._model_router
    if router is None:
        return {
            "enabled": False,
            "providers": [],
            "recent_decisions": [],
            "hardware": get_hardware_profiler().profile(refresh=refresh).to_routing_context(),
        }
    providers = router.list_providers()
    if refresh:
        snapshot = router.availability_snapshot(refresh=True)
        for provider in providers:
            provider["availability"] = snapshot[provider["id"]]
    return {
        "enabled": True,
        "strategy": router._strategy,
        "providers": providers,
        "fallback": router.fallback_stats(),
        "recent_decisions": router.routing_history(limit=20),
        "hardware": get_hardware_profiler().profile(refresh=refresh).to_routing_context(),
    }


@router.post("/circuit-breaker/reset")
async def reset_circuit_breaker(request: Request, provider_id: Optional[str] = Query(None)):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    params = {"provider_id": provider_id} if provider_id else {}
    result = await get_gateway().execute("circuit_breaker.reset_model", params, {"identity": identity})
    resp = _gateway_response(result)
    if resp:
        return resp
    return result.data


@router.get("/last-execution")
def get_last_execution():
    orch = get_orchestrator()
    record = orch.get_last_execution()
    if record is None:
        return {"execution": None}
    return {
        "execution": {
            "execution_id": record.execution_id,
            "timestamp": record.timestamp,
            "utterance": record.utterance,
            "intent": record.intent,
            "plan": record.plan,
            "decision": record.decision,
            "context_summary": record.context_summary,
            "step_results": record.step_results,
            "tool_result": record.tool_result,
            "error": record.error,
            "duration_ms": record.duration_ms,
        }
    }


@router.get("/rate-limiter/stats")
def get_rate_limiter_stats():
    orch = get_orchestrator()
    rl = getattr(orch, "_rate_limiter", None)
    if rl is None:
        return {"enabled": False}
    return {"enabled": True, **rl.stats()}


@router.post("/rate-limiter/clear")
async def clear_rate_limiter(request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    result = await get_gateway().execute("rate_limiter.clear", {}, {"identity": identity})
    resp = _gateway_response(result)
    if resp:
        return resp
    return result.data


@router.post("/process/offline")
async def process_offline(body: dict, request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    utterance = body.get("utterance", "")
    if not utterance:
        return JSONResponse({"error": "utterance is required"}, status_code=400)
    result = await get_gateway().execute("process.offline", body, {"identity": identity})
    resp = _gateway_response(result)
    if resp:
        return resp
    return result.data


@router.get("/offline-queue")
def get_offline_queue(status: Optional[str] = Query(None), operation_type: Optional[str] = Query(None)):
    orch = get_orchestrator()
    q = getattr(orch, "_offline_queue", None)
    if q is None:
        return {"enabled": False, "items": []}
    from sentinel.core.offline_queue import QueueStatus

    st = QueueStatus(status) if status else None
    items = q.list_items(status=st, operation_type=operation_type)
    stats = q.stats()
    return {"enabled": True, "items": items, "stats": stats}


@router.post("/offline-queue/sync")
async def sync_offline_queue(request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    result = await get_gateway().execute("offline_queue.sync", {}, {"identity": identity})
    resp = _gateway_response(result)
    if resp:
        return resp
    return result.data


@router.post("/offline-queue/clear")
async def clear_offline_queue(request: Request, status: Optional[str] = Query(None)):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    params = {"status": status} if status else {}
    result = await get_gateway().execute("offline_queue.clear", params, {"identity": identity})
    resp = _gateway_response(result)
    if resp:
        return resp
    return result.data


@router.get("/network/status")
async def get_network_status():
    orch = get_orchestrator()
    nm = getattr(orch, "_network_monitor", None)
    if nm is None:
        return {"monitored": False}
    online = await nm.check()
    return {"monitored": True, "online": online}


@router.get("/fallback/stats")
def get_fallback_stats():
    orch = get_orchestrator()
    mr = getattr(orch, "_model_router", None)
    if mr is None:
        return {"enabled": False}
    return {"enabled": True, **mr.fallback_stats()}


@router.post("/fallback/reset-stats")
async def reset_fallback_stats(request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    result = await get_gateway().execute("fallback.reset_stats", {}, {"identity": identity})
    resp = _gateway_response(result)
    if resp:
        return resp
    return result.data


@router.get("/skills")
def list_skills(category: Optional[str] = Query(None)):
    orch = get_orchestrator()
    se = getattr(orch, "_skill_engine", None)
    if se is None:
        return {"enabled": False, "skills": []}
    skills = se.registry.list(category=category)
    return {"enabled": True, "skills": [s.to_dict() for s in skills], "total": len(skills)}


@router.get("/skills/find")
def find_skills(q: str = Query("")):
    orch = get_orchestrator()
    se = getattr(orch, "_skill_engine", None)
    if se is None:
        return {"enabled": False, "skills": []}
    if not q:
        return {"enabled": True, "skills": [], "total": 0}
    skills = se.registry.find(q)
    return {"enabled": True, "skills": [s.to_dict() for s in skills], "total": len(skills)}


@router.post("/skills/suggest")
async def suggest_skill(body: dict, request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    task = body.get("task", "")
    if not task:
        return {"success": False, "error": "task is required"}
    result = await get_gateway().execute("skill.suggest", body, {"identity": identity})
    resp = _gateway_response(result)
    if resp:
        return resp
    return result.data


@router.post("/skills/execute")
async def execute_skill(body: dict, request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    skill_id = body.get("skill_id", "")
    if not skill_id:
        return {"success": False, "error": "skill_id is required"}
    result = await get_gateway().execute("skill.execute", body, {"identity": identity, "session_id": body.get("session_id")})
    resp = _gateway_response(result)
    if resp:
        return resp
    return result.data


@router.get("/alerts")
def list_alerts(
    source: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    acknowledged: Optional[bool] = Query(None),
    limit: int = Query(100),
):
    orch = get_orchestrator()
    am = getattr(orch, "_alert_manager", None)
    if am is None:
        return {"enabled": False, "alerts": []}
    from sentinel.core.alerting import AlertSeverity

    sev = AlertSeverity(severity) if severity else None
    alerts = am.list(source=source, severity=sev, acknowledged=acknowledged, limit=limit)
    return {"alerts": alerts, "stats": am.stats()}


@router.post("/alerts/acknowledge")
async def acknowledge_alert(body: dict, request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    result = await get_gateway().execute("alert.acknowledge", body, {"identity": identity})
    resp = _gateway_response(result)
    if resp:
        return resp
    return result.data


@router.post("/alerts/check")
async def check_alerts(request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    result = await get_gateway().execute("alert.check", {}, {"identity": identity})
    resp = _gateway_response(result)
    if resp:
        return resp
    return result.data


@router.post("/alerts/clear")
async def clear_alerts(request: Request, acknowledged_only: bool = Query(True)):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    result = await get_gateway().execute("alert.clear", {"acknowledged_only": acknowledged_only}, {"identity": identity})
    resp = _gateway_response(result)
    if resp:
        return resp
    return result.data


# ── Knowledge Base endpoints ────────────────────────────────────────────────


def _get_kb(orch):
    return getattr(orch, "_knowledge_base", None) or getattr(orch._tool_gateway, "_knowledge_base", None)


@router.post("/kb/search")
def kb_search(body: dict):
    orch = get_orchestrator()
    kb = _get_kb(orch)
    if kb is None:
        return {"enabled": False}
    query = body.get("query", "")
    k = body.get("k", 5)
    if not query:
        return {"error": "query is required"}
    results = kb.search(query, k=k)
    return {
        "results": [{"text": r.text, "source": r.source, "score": round(r.score, 4)} for r in results],
        "count": len(results),
    }


@router.post("/kb/add")
async def kb_add(body: dict, request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    text = body.get("text", "")
    if not text:
        return JSONResponse({"error": "text is required"}, status_code=400)
    result = await get_gateway().execute("kb.add", body, {"identity": identity})
    resp = _gateway_response(result)
    if resp:
        return resp
    return result.data


@router.post("/kb/add-file")
async def kb_add_file(body: dict, request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    path = body.get("path", "")
    if not path:
        return JSONResponse({"error": "path is required"}, status_code=400)
    if not os.path.exists(path):
        return JSONResponse({"error": f"File not found: {path}"}, status_code=400)
    result = await get_gateway().execute("kb.add_file", body, {"identity": identity})
    resp = _gateway_response(result)
    if resp:
        return resp
    return result.data


@router.get("/kb/list")
def kb_list():
    orch = get_orchestrator()
    kb = _get_kb(orch)
    if kb is None:
        return {"enabled": False, "documents": []}
    docs = kb.list_documents()
    return {
        "documents": [
            {"doc_id": d.doc_id, "source": d.source, "chunks": d.chunks, "created_at": d.created_at} for d in docs
        ],
        "total": len(docs),
    }


@router.delete("/kb/{doc_id}")
async def kb_delete(doc_id: str, request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    result = await get_gateway().execute("kb.delete", {"doc_id": doc_id}, {"identity": identity})
    resp = _gateway_response(result, not_found=True)
    if resp:
        return resp
    return result.data


@router.post("/kb/clear")
async def kb_clear(request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    result = await get_gateway().execute("kb.clear", {}, {"identity": identity})
    resp = _gateway_response(result)
    if resp:
        return resp
    return result.data


@router.get("/kb/stats")
def kb_stats():
    orch = get_orchestrator()
    kb = _get_kb(orch)
    if kb is None:
        return {"enabled": False}
    return {"enabled": True, **kb.stats()}


@router.post("/kb/rebuild")
async def kb_rebuild(request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    result = await get_gateway().execute("kb.rebuild", {}, {"identity": identity})
    resp = _gateway_response(result)
    if resp:
        return resp
    return result.data


@router.post("/kb/query")
def kb_query(body: dict):
    orch = get_orchestrator()
    kb = _get_kb(orch)
    if kb is None:
        return {"enabled": False, "context": ""}
    query = body.get("query", "")
    k = body.get("k", 5)
    if not query:
        return {"error": "query is required"}
    context = kb.query(query, k=k)
    return {"context": context, "has_results": bool(context)}


# ── File Pipeline endpoints ─────────────────────────────────────────────────


def _get_pipeline(orch):
    return getattr(orch, "_file_pipeline", None) or getattr(orch._tool_gateway, "_file_pipeline", None)


@router.post("/pipeline/ingest")
async def pipeline_ingest(body: dict, request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    path = body.get("path", "")
    if not path:
        return JSONResponse({"error": "path is required"}, status_code=400)
    result = await get_gateway().execute("pipeline.ingest", body, {"identity": identity})
    resp = _gateway_response(result)
    if resp:
        return resp
    return result.data


@router.get("/pipeline/status")
def pipeline_status():
    orch = get_orchestrator()
    fp = _get_pipeline(orch)
    if fp is None:
        return {"enabled": False}
    return {"enabled": True, **fp.stats()}


@router.post("/pipeline/reset-stats")
async def pipeline_reset_stats(request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    result = await get_gateway().execute("pipeline.reset_stats", {}, {"identity": identity})
    resp = _gateway_response(result)
    if resp:
        return resp
    return result.data


# ── Web Browsing endpoints ──────────────────────────────────────────────────


def _get_web(orch):
    return getattr(orch, "_web_browsing", None) or getattr(orch._tool_gateway, "_web_browsing", None)


@router.post("/web/navigate")
async def web_navigate(body: dict, request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    url = body.get("url", "")
    if not url:
        return JSONResponse({"error": "url is required"}, status_code=400)
    result = await get_gateway().execute("web.navigate", body, {"identity": identity})
    resp = _gateway_response(result)
    if resp:
        return resp
    return result.data


@router.post("/web/extract")
async def web_extract(body: dict, request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    url = body.get("url", "")
    if not url:
        return JSONResponse({"error": "url is required"}, status_code=400)
    result = await get_gateway().execute("web.extract", body, {"identity": identity})
    resp = _gateway_response(result)
    if resp:
        return resp
    return result.data


@router.get("/web/search")
def web_search(query: str = "", num_results: int = 5):
    orch = get_orchestrator()
    wb = _get_web(orch)
    if wb is None:
        return {"enabled": False}
    if not query:
        return {"error": "query is required"}
    num_results = min(num_results, 20)
    results = wb.search_web(query, num_results=num_results)
    return {"query": query, "results": results, "count": len(results)}


@router.get("/web/status")
def web_status():
    orch = get_orchestrator()
    wb = _get_web(orch)
    if wb is None:
        return {"enabled": False}
    return {"enabled": True, **wb.stats()}


# ── Hardening / Health endpoints ────────────────────────────────────────────


def _get_hardening(orch):
    return getattr(orch, "_hardening", None) or getattr(orch._tool_gateway, "_hardening", None)


@router.get("/hardening/config")
def hardening_config(request: Request):
    _require_admin(request)
    orch = get_orchestrator()
    h = _get_hardening(orch)
    if h is None:
        return {"enabled": False}
    return {"enabled": True, **h.stats()}


@router.put("/hardening/config")
async def hardening_update_config(body: dict, request: Request):
    from modules import get_gateway

    _require_admin(request)
    identity = request_identity(request).to_dict()
    params = {"action": "set"}
    key_map = {
        "default_timeout_seconds": "timeout_seconds",
        "default_circuit_breaker_threshold": "circuit_breaker_threshold",
        "default_circuit_breaker_cooldown": "circuit_breaker_cooldown",
        "default_retry_jitter": "retry_jitter",
    }
    for old_key, new_key in key_map.items():
        if old_key in body:
            params[new_key] = body[old_key]
    result = await get_gateway().execute("hardening.config", params, {"identity": identity})
    resp = _gateway_response(result)
    if resp:
        return resp
    return result.data


@router.put("/hardening/tool-override/{tool_id}")
async def hardening_tool_override(tool_id: str, body: dict, request: Request):
    from modules import get_gateway

    _require_admin(request)
    identity = request_identity(request).to_dict()
    params = {"action": "tool_override", "tool_id": tool_id}
    for key in ("timeout_seconds", "circuit_breaker_threshold", "circuit_breaker_cooldown", "retry_jitter"):
        if key in body:
            params[key] = body[key]
    result = await get_gateway().execute("hardening.config", params, {"identity": identity})
    resp = _gateway_response(result)
    if resp:
        return resp
    return result.data


@router.delete("/hardening/tool-override/{tool_id}")
async def hardening_remove_override(tool_id: str, request: Request):
    from modules import get_gateway

    _require_admin(request)
    identity = request_identity(request).to_dict()
    params = {"action": "remove_override", "tool_id": tool_id}
    result = await get_gateway().execute("hardening.config", params, {"identity": identity})
    resp = _gateway_response(result)
    if resp:
        return resp
    return result.data


@router.post("/hardening/circuit-breaker/reset")
async def hardening_reset_circuits(request: Request, body: Optional[dict] = None):
    from modules import get_gateway

    _require_admin(request)
    identity = request_identity(request).to_dict()
    params = {"tool_id": (body or {}).get("tool_id", "")}
    result = await get_gateway().execute("hardening.reset", params, {"identity": identity})
    resp = _gateway_response(result)
    if resp:
        return resp
    return result.data


@router.get("/hardening/health")
def hardening_health(request: Request):
    _require_admin(request)
    orch = get_orchestrator()
    h = _get_hardening(orch)
    if h is None:
        return {"enabled": False}
    return {"enabled": True, **h.check_health()}


# ── Enhanced Profile endpoints ──────────────────────────────────────────────


def _get_profile_mgr():
    try:
        from modules.profile import _svc

        return _svc
    except Exception:
        return None


@router.get("/profile")
def profile_get(request: Request, user_id: str = ""):
    pm = _get_profile_mgr()
    if pm is None:
        return {"enabled": False}
    uid = _scoped_user_id(request, user_id)
    profile = pm.get_profile(uid)
    if profile is None:
        profile = pm.get_or_create_profile(uid)
    data = profile.to_dict()
    data["preferences"] = pm.get_all_preferences(uid)
    return data


@router.patch("/profile")
async def profile_update(body: dict, request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    uid = _scoped_user_id(request, str(body.get("user_id", "")))
    params = {"user_id": uid}
    allowed = {"username", "display_name", "avatar", "theme", "timezone", "locale", "bio", "tags"}
    for k, v in body.items():
        if k in allowed:
            params[k] = v
    result = await get_gateway().execute("profile.update", params, {"identity": identity})
    resp = _gateway_response(result)
    if resp:
        return resp
    return result.data


@router.get("/profile/preferences")
def profile_preferences(request: Request, user_id: str = ""):
    pm = _get_profile_mgr()
    if pm is None:
        return {"enabled": False}
    uid = _scoped_user_id(request, user_id)
    prefs = pm.get_all_preferences(uid)
    return {"preferences": prefs, "count": len(prefs)}


@router.put("/profile/preferences")
async def profile_set_preference(body: dict, request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    uid = _scoped_user_id(request, str(body.get("user_id", "")))
    key = body.get("key", "")
    if not key:
        return JSONResponse({"error": "key is required"}, status_code=400)
    params = {"action": "set", "user_id": uid, "key": key, "value": body.get("value")}
    result = await get_gateway().execute("profile.preference", params, {"identity": identity})
    resp = _gateway_response(result)
    if resp:
        return resp
    return result.data


@router.delete("/profile/preferences")
async def profile_delete_preference(request: Request, key: str = "", user_id: str = ""):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    uid = _scoped_user_id(request, user_id)
    if not key:
        return JSONResponse({"error": "key is required"}, status_code=400)
    params = {"action": "delete", "user_id": uid, "key": key}
    result = await get_gateway().execute("profile.preference", params, {"identity": identity})
    resp = _gateway_response(result)
    if resp:
        return resp
    return result.data


@router.get("/profile/history")
def profile_history(request: Request, user_id: str = "", limit: int = 50):
    pm = _get_profile_mgr()
    if pm is None:
        return {"enabled": False}
    uid = _scoped_user_id(request, user_id)
    history = pm.get_profile_history(uid, limit=limit)
    return {"history": history, "count": len(history)}


@router.get("/profile/export")
def profile_export(request: Request, user_id: str = ""):
    pm = _get_profile_mgr()
    if pm is None:
        return {"enabled": False}
    uid = _scoped_user_id(request, user_id)
    data = pm.export_profile(uid)
    return data


@router.post("/profile/import")
async def profile_import(body: dict, request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    uid = _scoped_user_id(request, str(body.get("user_id", "")))
    params = {"user_id": uid, "data": body.get("data", body)}
    result = await get_gateway().execute("profile.import", params, {"identity": identity})
    resp = _gateway_response(result)
    if resp:
        return resp
    return result.data


@router.get("/profile/presets")
def profile_presets(request: Request, user_id: str = ""):
    pm = _get_profile_mgr()
    if pm is None:
        return {"enabled": False}
    uid = _scoped_user_id(request, user_id)
    presets = pm.list_presets(uid)
    return {"presets": presets, "count": len(presets)}


@router.post("/profile/presets")
async def profile_save_preset(body: dict, request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    uid = _scoped_user_id(request, str(body.get("user_id", "")))
    preset_name = body.get("preset_name", "")
    if not preset_name:
        return JSONResponse({"error": "preset_name is required"}, status_code=400)
    params = {"action": "save", "user_id": uid, "preset_name": preset_name, "description": body.get("description", "")}
    result = await get_gateway().execute("profile.preset", params, {"identity": identity})
    resp = _gateway_response(result)
    if resp:
        return resp
    return result.data


@router.post("/profile/presets/apply")
async def profile_apply_preset(body: dict, request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    uid = _scoped_user_id(request, str(body.get("user_id", "")))
    preset_name = body.get("preset_name", "")
    if not preset_name:
        return JSONResponse({"error": "preset_name is required"}, status_code=400)
    params = {"action": "apply", "user_id": uid, "preset_name": preset_name}
    result = await get_gateway().execute("profile.preset", params, {"identity": identity})
    resp = _gateway_response(result)
    if resp:
        return resp
    return result.data


@router.delete("/profile/presets")
async def profile_delete_preset(body: dict, request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    uid = _scoped_user_id(request, str(body.get("user_id", "")))
    preset_name = body.get("preset_name", "")
    if not preset_name:
        return JSONResponse({"error": "preset_name is required"}, status_code=400)
    params = {"action": "delete", "user_id": uid, "preset_name": preset_name}
    result = await get_gateway().execute("profile.preset", params, {"identity": identity})
    resp = _gateway_response(result)
    if resp:
        return resp
    return result.data


@router.get("/profile/search")
def profile_search(request: Request, query: str = "", limit: int = 20):
    _require_admin(request)
    pm = _get_profile_mgr()
    if pm is None:
        return {"enabled": False, "results": []}
    if not query:
        return {"error": "query is required", "results": []}
    results = pm.search_profiles(query, limit=limit)
    return {"results": results, "count": len(results)}
