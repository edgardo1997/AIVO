import asyncio
import json
import logging
import os
import uuid
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response

log = logging.getLogger("sentinel.sentinel_bridge")

router = APIRouter()


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
        body.get("path", ""), recursive=body.get("recursive", True),
        max_files=int(body.get("max_files", 25)),
        expected_output_tokens=int(body.get("expected_output_tokens", 1200)),
    )


@router.post("/reports/export")
async def export_report(body: dict, request: Request):
    content, media_type, filename = _file_pipeline().export_report(
        str(body.get("report", "")), str(body.get("format", "markdown")),
    )
    return Response(content=content, media_type=media_type,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _require_admin() -> None:
    from modules.permissions import _svc as perm_svc
    level = perm_svc.repo.load().get("level", "confirm")
    if level != "admin":
        raise HTTPException(status_code=403, detail=f"Admin level required, current level: {level}")


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
    return {
        "execution_id": record.execution_id, "timestamp": record.timestamp,
        "utterance": record.utterance, "intent": record.intent,
        "tool_result": record.tool_result, "error": record.error,
        "duration_ms": record.duration_ms,
        "session_id": record.context_summary.get("session_id"),
    }


def _step_result(step) -> Dict[str, Any]:
    return {
        "step_id": step.step_id, "tool_id": step.tool_id, "success": step.success,
        "data": step.data, "error": step.error, "duration_ms": step.duration_ms,
        "attempts": step.attempts, "recovery_strategy": step.recovery_strategy,
        "executed_tool_id": step.executed_tool_id, "status": step.status,
    }


@router.post("/memory/sessions")
async def create_memory_session(body: dict, request: Request):
    return {"session_id": uuid.uuid4().hex[:16], "label": str(body.get("label", ""))[:100]}


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
    owned = {item["session_id"] for item in memory.list_sessions(identity["user_id"], limit=200)}
    if session_id not in owned:
        return JSONResponse(status_code=404, content={"error": "Session not found"})
    records = memory.get_session_history(session_id, limit=limit)
    return {"session_id": session_id, "records": [_memory_record(record) for record in reversed(records)]}


@router.get("/memory/search")
async def search_memory(request: Request, q: str = Query("", min_length=1), limit: int = Query(50, ge=1, le=200)):
    from modules.auth import request_identity
    identity = request_identity(request).to_dict()
    memory = get_memory() or get_orchestrator()._memory
    return {"results": [_memory_record(record) for record in memory.search_memory(identity["user_id"], q, limit)]}


@router.delete("/memory/sessions/{session_id}")
async def delete_memory_session(session_id: str, request: Request):
    from modules.auth import request_identity
    identity = request_identity(request).to_dict()
    memory = get_memory() or get_orchestrator()._memory
    deleted = memory.delete_session(session_id, identity["user_id"])
    if not deleted:
        return JSONResponse(status_code=404, content={"error": "Session not found"})
    try:
        from modules.audit import _svc as audit_service
        audit_service.log_action("memory_session_delete", session_id, "success", user=identity["user_id"])
    except Exception:
        pass
    return {"deleted": True, "session_id": session_id, "records_deleted": deleted}


@router.get("/permissions/rules")
async def list_granular_permission_rules(request: Request):
    from modules.permissions import _svc
    return {"rules": _svc.list_rules()}


@router.post("/permissions/rules")
async def add_granular_permission_rule(body: dict, request: Request):
    _require_admin()
    from modules.permissions import _svc
    try:
        return {"rule": _svc.add_rule(body)}
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})


@router.delete("/permissions/rules/{rule_id}")
async def delete_granular_permission_rule(rule_id: str, request: Request):
    _require_admin()
    from modules.permissions import _svc
    if not _svc.remove_rule(rule_id):
        return JSONResponse(status_code=404, content={"error": "Rule not found"})
    return {"deleted": True, "rule_id": rule_id}


@router.post("/process")
async def process_utterance(body: dict, request: Request):
    from modules.auth import request_identity

    orch = get_orchestrator()
    utterance = body.get("utterance", "")
    if not utterance:
        return {"error": "utterance is required"}
    session_id = body.get("session_id")
    dry_run = body.get("dry_run", False)
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
        } if result.tool_result else None,
        "step_results": [_step_result(s) for s in result.step_results] if result.step_results else None,
        "rollback_actions": result.rollback_actions,
        "advisory": result.advisory.to_dict() if result.advisory else None,
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
        "sub_task_results": [
            {
                "sub_task_id": s.step_id,
                "success": s.success,
                "error": s.error,
                "duration_ms": s.duration_ms,
            }
            for s in result.step_results
        ] if result.step_results else [],
    }


# ── Vault endpoints ──────────────────────────────────────────
@router.get("/vault/entries")
async def vault_list(category: str = ""):
    vault = get_vault_manager()
    entries = vault.list_entries(category)
    return {"entries": [e.to_dict() for e in entries], "total": len(entries)}


@router.get("/vault/entries/{vault_id}")
async def vault_get(vault_id: str):
    vault = get_vault_manager()
    entry = vault.get_entry(vault_id)
    if not entry:
        return {"error": "not found"}, 404
    return {"entry": entry.to_dict()}


@router.post("/vault/entries")
async def vault_create(body: dict):
    from sentinel.core.vault import VaultEntry
    vault = get_vault_manager()
    entry = VaultEntry.from_dict(body)
    result = vault.create_entry(entry)
    if not result:
        return {"error": "create failed"}, 400
    return {"status": "created", "id": result}


@router.patch("/vault/entries/{vault_id}")
async def vault_update(vault_id: str, body: dict):
    vault = get_vault_manager()
    ok = vault.update_entry(vault_id, **body)
    if not ok:
        return {"error": "not found"}, 404
    return {"status": "updated"}


@router.delete("/vault/entries/{vault_id}")
async def vault_delete(vault_id: str):
    vault = get_vault_manager()
    ok = vault.delete_entry(vault_id)
    if not ok:
        return {"error": "not found"}, 404
    return {"status": "deleted"}


@router.post("/vault/entries/{vault_id}/reveal")
async def vault_reveal(vault_id: str):
    vault = get_vault_manager()
    value = vault.reveal_value(vault_id)
    if value is None:
        return {"error": "not found"}, 404
    return {"value": value}


@router.post("/vault/entries/{vault_id}/rotate")
async def vault_rotate_secret(vault_id: str):
    vault = get_vault_manager()
    ok = vault.rotate_secret(vault_id)
    if not ok:
        return {"error": "not found or no value"}, 404
    return {"status": "rotated"}


@router.post("/vault/rotate-master-key")
async def vault_rotate_master():
    vault = get_vault_manager()
    ok = vault.rotate_master_key()
    if not ok:
        return {"error": "cryptography not available"}, 400
    return {"status": "master_key_rotated"}


@router.get("/vault/audit")
async def vault_audit(vault_id: str = "", limit: int = 50):
    vault = get_vault_manager()
    entries = vault.get_audit_log(vault_id, limit)
    return {"audit": [e.__dict__ for e in entries]}


@router.get("/vault/status")
async def vault_status():
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


def _build_chat_pipeline_trace(result) -> Dict[str, Any]:
    plan = result.plan
    return {
        "intent": {
            "action": plan.intent.action,
            "target": plan.intent.target,
            "confidence": plan.intent.confidence,
            "raw_input": plan.intent.raw_input,
        },
        "decision": {
            "decision": result.decision.decision if result.decision else None,
            "final_risk_score": result.decision.final_risk_score if result.decision else None,
            "reason": result.decision.reason if result.decision else None,
        } if result.decision else None,
        "advisory": result.advisory.to_dict() if result.advisory else None,
        "tool_result": {
            "success": result.tool_result.success if result.tool_result else None,
            "tool_id": result.tool_result.tool_id if result.tool_result else None,
        } if result.tool_result else None,
        "simulated": result.simulated,
        "approved": result.approved,
        "blocked": result.blocked,
        "action_id": result.action_id,
        "simulation_summary": result.simulation_summary,
        "error": result.error,
    }


@router.post("/chat")
async def sentinel_chat(body: dict, request: Request):
    from modules.auth import request_identity
    from modules.ai_provider import _svc as ai_svc

    orch = get_orchestrator()
    identity = request_identity(request).to_dict()
    message = body.get("message", "")
    history = body.get("context", [])
    session_id = body.get("session_id")

    if not message:
        return {"response": "Please provide a message.", "provider": None, "model": None, "pipeline": None}

    result = await orch.process(message, identity=identity, session_id=session_id)
    intent = result.plan.intent
    pipeline_summary = _build_pipeline_summary(result)
    pipeline_trace = _build_chat_pipeline_trace(result)

    actionable = intent.confidence >= 0.6

    _AI_TIMEOUT = 30

    if actionable and result.tool_result and result.tool_result.success:
        tool_data = result.tool_result.data
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
                ),
                timeout=_AI_TIMEOUT,
            )
            response_text = fmt_response.get("response", "")
            provider = fmt_response.get("provider")
            model = fmt_response.get("model")
        except asyncio.TimeoutError:
            log.warning("AI formatting timed out, using raw tool data")
            response_text = json.dumps(tool_data, indent=2) if tool_data else "Task completed."
            provider = None
            model = None
        except Exception as e:
            log.warning("AI formatting failed for tool result, using raw data: %s", e)
            response_text = json.dumps(tool_data, indent=2) if tool_data else "Task completed."
            provider = None
            model = None
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
        except asyncio.TimeoutError:
            log.error("AI chat timed out")
            response_text = "I'm sorry, the AI provider did not respond in time. Please check your AI configuration."
            provider = None
            model = None
        except Exception as e:
            log.error("AI chat failed: %s", e)
            response_text = f"Error connecting to AI. Provider may not be configured. Details: {e}"
            provider = None
            model = None

    return {
        "response": response_text,
        "provider": provider,
        "model": model,
        "pipeline": pipeline_trace,
    }


@router.get("/capabilities")
def get_capabilities():
    orch = get_orchestrator()
    return orch.get_capabilities()


@router.get("/goals")
def get_goals():
    goal_registry = get_goal_registry()
    if goal_registry is None:
        return {"goals": []}
    return {
        "goals": [g.to_dict() for g in goal_registry.list_all()]
    }


@router.post("/goals")
def post_goal(body: dict):
    try:
        _require_admin()
    except PermissionError as e:
        return JSONResponse({"error": str(e)}, status_code=403)
    goal_registry = get_goal_registry()
    if goal_registry is None:
        get_orchestrator()
        goal_registry = get_goal_registry()
    from sentinel.core.goals import GoalDefinition, RiskLevel
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
    if not goal_registry._test_skip_cap_validation:
        invalid = _validate_capabilities(caps)
        if invalid:
            return JSONResponse({"error": f"unknown capabilities: {invalid}"}, status_code=400)
    risk_str = body.get("base_risk", "low")
    if risk_str not in ("low", "medium", "high", "critical"):
        return JSONResponse({"error": f"invalid base_risk: {risk_str}"}, status_code=400)
    if goal_registry.get(gid) is not None:
        return JSONResponse({"error": f"goal '{gid}' already exists"}, status_code=409)
    goal = GoalDefinition(
        id=gid,
        name=body.get("name", gid),
        description=body.get("description", ""),
        related_intents=intent_targets,
        possible_capabilities=caps,
        priority=priority,
        base_risk=RiskLevel(risk_str),
        keywords=body.get("keywords", []),
    )
    goal_registry.register(goal, source="api")
    return JSONResponse({"status": "registered", "goal_id": gid}, status_code=201)


@router.delete("/goals/{goal_id}")
def delete_goal(goal_id: str):
    try:
        _require_admin()
    except PermissionError as e:
        return JSONResponse({"error": str(e)}, status_code=403)
    goal_registry = get_goal_registry()
    if goal_registry is None:
        get_orchestrator()
        goal_registry = get_goal_registry()
    try:
        goal_registry.unregister(goal_id, source="api")
        return {"status": "deleted", "goal_id": goal_id}
    except KeyError:
        return JSONResponse({"error": f"goal '{goal_id}' not found"}, status_code=404)


@router.patch("/goals/{goal_id}")
def patch_goal(goal_id: str, body: dict):
    try:
        _require_admin()
    except PermissionError as e:
        return JSONResponse({"error": str(e)}, status_code=403)
    goal_registry = get_goal_registry()
    if goal_registry is None:
        get_orchestrator()
        goal_registry = get_goal_registry()
    if goal_registry.get(goal_id) is None:
        return JSONResponse({"error": f"goal '{goal_id}' not found"}, status_code=404)
    clen = body.get("priority")
    if clen is not None and not (0 <= clen <= 10):
        return JSONResponse({"error": "priority must be 0-10"}, status_code=400)
    allowed = {"name", "description", "related_intents", "possible_capabilities",
               "priority", "base_risk", "keywords", "enabled", "context_rules"}
    changes = {k: v for k, v in body.items() if k in allowed and v is not None}
    if not changes:
        return JSONResponse({"error": "no valid fields to update"}, status_code=400)
    if "possible_capabilities" in changes and not goal_registry._test_skip_cap_validation:
        invalid = _validate_capabilities(changes["possible_capabilities"])
        if invalid:
            return JSONResponse({"error": f"unknown capabilities: {invalid}"}, status_code=400)
    from sentinel.core.goals import RiskLevel
    if "base_risk" in changes:
        rv = changes["base_risk"]
        if rv not in ("low", "medium", "high", "critical"):
            return JSONResponse({"error": f"invalid base_risk: {rv}"}, status_code=400)
        changes["base_risk"] = RiskLevel(rv)
    goal_registry.update(goal_id, changes, source="api")
    return {"status": "updated", "goal_id": goal_id}


@router.get("/goals/audit")
def get_goal_audit():
    try:
        _require_admin()
    except PermissionError as e:
        return JSONResponse({"error": str(e)}, status_code=403)
    goal_registry = get_goal_registry()
    if goal_registry is None:
        get_orchestrator()
        goal_registry = get_goal_registry()
    return {"audit_log": [
        {"timestamp": e.timestamp, "operation": e.operation,
         "goal_id": e.goal_id, "source": e.source, "details": e.details}
        for e in goal_registry.get_audit_log()
    ]}


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
    from modules.auth import request_identity
    orch = get_orchestrator()
    action_id = body.get("action_id", "")
    if not action_id:
        return JSONResponse({"error": "action_id is required"}, status_code=400)
    approved = body.get("approved", True)
    result = await orch.approve_execution(
        action_id, approved=approved,
        approver_identity=request_identity(request).to_dict(),
    )
    plan = result.plan
    return {
        "blocked": result.blocked,
        "approved": result.approved,
        "action_id": result.action_id,
        "error": result.error,
        "simulation_summary": result.simulation_summary,
        "decision": result.decision.decision if result.decision else None,
        "decision_reason": result.decision.reason if result.decision else None,
        "intent": {
            "action": plan.intent.action,
            "target": plan.intent.target,
            "parameters": plan.intent.parameters,
            "confidence": plan.intent.confidence,
            "raw_input": plan.intent.raw_input,
        },
        "tool_result": {
            "success": result.tool_result.success if result.tool_result else None,
            "data": result.tool_result.data if result.tool_result else None,
            "error": result.tool_result.error if result.tool_result else None,
            "requires_confirmation": result.tool_result.requires_confirmation if result.tool_result else False,
            "duration_ms": result.tool_result.duration_ms if result.tool_result else None,
        } if result.tool_result else None,
        "step_results": [_step_result(s) for s in result.step_results] if result.step_results else None,
        "rollback_actions": result.rollback_actions,
    }


@router.post("/simulate/modify-and-approve")
async def modify_and_approve(body: dict, request: Request):
    from modules.auth import request_identity
    orch = get_orchestrator()
    action_id = body.get("action_id", "")
    if not action_id:
        return JSONResponse({"error": "action_id is required"}, status_code=400)
    steps = body.get("steps", [])
    if not steps:
        return {"error": "steps are required", "approved": False, "action_id": action_id}
    result = await orch.approve_with_modifications(
        action_id, steps,
        approver_identity=request_identity(request).to_dict(),
    )
    return {
        "blocked": result.blocked,
        "approved": result.approved,
        "action_id": result.action_id,
        "error": result.error,
        "step_results": [_step_result(s) for s in result.step_results] if result.step_results else None,
        "rollback_actions": result.rollback_actions,
        "modified": True,
        "requires_reconfirmation": result.blocked and bool(result.action_id),
    }


@router.post("/simulate/reject")
async def reject_execution(body: dict, request: Request):
    from modules.auth import request_identity
    orch = get_orchestrator()
    action_id = body.get("action_id", "")
    if not action_id:
        return JSONResponse({"error": "action_id is required"}, status_code=400)
    result = await orch.approve_execution(
        action_id, approved=False,
        approver_identity=request_identity(request).to_dict(),
    )
    return {
        "blocked": False,
        "approved": False,
        "action_id": action_id,
        "error": result.error,
    }


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
def create_budget(body: dict):
    from sentinel.core.cost_tracker import BudgetConfig
    orch = get_orchestrator()
    ct = orch.cost_tracker
    if ct is None:
        return JSONResponse({"error": "Cost tracker not available"}, status_code=400)
    name = body.get("name", "")
    if not name:
        return JSONResponse({"error": "name is required"}, status_code=400)
    ct.set_budget(BudgetConfig(
        name=name,
        max_cost_usd=float(body.get("max_cost_usd", 0)),
        period=body.get("period", "monthly"),
        provider_id=body.get("provider_id"),
        max_tokens=body.get("max_tokens"),
        enabled=body.get("enabled", True),
    ))
    return {"success": True, "name": name}


@router.delete("/cost/budgets/{name}")
def delete_budget(name: str):
    orch = get_orchestrator()
    ct = orch.cost_tracker
    if ct is None:
        return JSONResponse({"error": "Cost tracker not available"}, status_code=400)
    ct.delete_budget(name)
    return {"success": True}


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
def clear_cache():
    orch = get_orchestrator()
    pc = orch.plan_cache
    if pc is None:
        return {"cleared": False}
    count = pc.clear()
    return {"cleared": True, "entries_removed": count}


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
        "latency_baselines": [
            {**asdict(row), "task_type": row.task_type.value} for row in baselines[:50]
        ],
        "alerts": alert_manager.stats() if alert_manager is not None else {
            "total": 0, "unacknowledged": 0, "by_source": {}
        },
    }


@router.get("/observability/traces")
def get_observability_traces(
    limit: int = Query(100, ge=1, le=500), tool_id: Optional[str] = Query(None),
):
    orch = get_orchestrator()
    service = getattr(orch._tool_gateway, "_observability", None)
    if service is None:
        return {"traces": [], "summary": {}}
    return {"traces": service.traces(limit=limit, tool_id=tool_id),
            "summary": service.summary()}


@router.post("/recovery/circuit-breaker/reset")
def reset_recovery_circuit(body: dict):
    """Reset one explicitly typed circuit; avoids ambiguous cross-resource resets."""
    resource_type = str(body.get("resource_type", "")).strip().lower()
    resource_id = str(body.get("resource_id", "")).strip()
    if resource_type not in ("model", "tool") or not resource_id:
        raise HTTPException(status_code=400, detail="resource_type (model|tool) and resource_id are required")
    orch = get_orchestrator()
    if resource_type == "model":
        router_service = getattr(orch, "_model_router", None)
        count = router_service.circuit_breaker.reset(resource_id) if router_service else 0
    else:
        hardening = _get_hardening(orch)
        count = hardening.circuit_breaker.reset(resource_id) if hardening else 0
    return {"resource_type": resource_type, "resource_id": resource_id, "circuits_reset": count}


@router.get("/model-router/status")
def get_model_router_status(refresh: bool = Query(False)):
    """Expose routing readiness without leaking API keys."""
    router = get_orchestrator()._model_router
    if router is None:
        return {"enabled": False, "providers": [], "recent_decisions": []}
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
    }


@router.post("/circuit-breaker/reset")
def reset_circuit_breaker(provider_id: Optional[str] = Query(None)):
    orch = get_orchestrator()
    total = 0
    if orch._model_router:
        total += orch._model_router.circuit_breaker.reset(provider_id=provider_id)
    return {"reset": total, "provider_id": provider_id}


@router.get("/last-execution")
def get_last_execution():
    orch = get_orchestrator()
    record = orch.get_last_execution()
    if record is None:
        return {"execution": None}
    return {"execution": {
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
    }}


@router.get("/rate-limiter/stats")
def get_rate_limiter_stats():
    orch = get_orchestrator()
    rl = getattr(orch, '_rate_limiter', None)
    if rl is None:
        return {"enabled": False}
    return {"enabled": True, **rl.stats()}


@router.post("/rate-limiter/clear")
def clear_rate_limiter():
    orch = get_orchestrator()
    rl = getattr(orch, '_rate_limiter', None)
    if rl is None:
        return {"cleared": False}
    count = rl.clear()
    return {"cleared": True, "buckets_removed": count}


@router.post("/process/offline")
async def process_offline(body: dict, request: Request):
    from modules.auth import request_identity
    orch = get_orchestrator()
    utterance = body.get("utterance", "")
    if not utterance:
        return {"error": "utterance is required"}
    session_id = body.get("session_id")
    result = await orch.process_offline(
        utterance,
        identity=request_identity(request).to_dict(),
        session_id=session_id,
    )
    return {
        "queued": result.action_id is not None,
        "item_id": result.action_id,
        "error": result.error,
    }


@router.get("/offline-queue")
def get_offline_queue(status: Optional[str] = Query(None), operation_type: Optional[str] = Query(None)):
    orch = get_orchestrator()
    q = getattr(orch, '_offline_queue', None)
    if q is None:
        return {"enabled": False, "items": []}
    from sentinel.core.offline_queue import QueueStatus
    st = QueueStatus(status) if status else None
    items = q.list_items(status=st, operation_type=operation_type)
    stats = q.stats()
    return {"enabled": True, "items": items, "stats": stats}


@router.post("/offline-queue/sync")
async def sync_offline_queue():
    orch = get_orchestrator()
    q = getattr(orch, '_offline_queue', None)
    if q is None:
        return {"synced": 0}
    stats = await orch._process_offline_queue()
    return stats


@router.post("/offline-queue/clear")
def clear_offline_queue(status: Optional[str] = Query(None)):
    orch = get_orchestrator()
    q = getattr(orch, '_offline_queue', None)
    if q is None:
        return {"cleared": 0}
    from sentinel.core.offline_queue import QueueStatus
    st = QueueStatus(status) if status else None
    count = q.clear(status=st)
    return {"cleared": count}


@router.get("/network/status")
async def get_network_status():
    orch = get_orchestrator()
    nm = getattr(orch, '_network_monitor', None)
    if nm is None:
        return {"monitored": False}
    online = await nm.check()
    return {"monitored": True, "online": online}


@router.get("/fallback/stats")
def get_fallback_stats():
    orch = get_orchestrator()
    mr = getattr(orch, '_model_router', None)
    if mr is None:
        return {"enabled": False}
    return {"enabled": True, **mr.fallback_stats()}


@router.post("/fallback/reset-stats")
def reset_fallback_stats():
    orch = get_orchestrator()
    mr = getattr(orch, '_model_router', None)
    if mr is None:
        return {"reset": 0}
    count = mr.reset_fallback_stats()
    return {"reset": count}


@router.get("/skills")
def list_skills(category: Optional[str] = Query(None)):
    orch = get_orchestrator()
    se = getattr(orch, '_skill_engine', None)
    if se is None:
        return {"enabled": False, "skills": []}
    skills = se.registry.list(category=category)
    return {"enabled": True, "skills": [s.to_dict() for s in skills], "total": len(skills)}


@router.get("/skills/find")
def find_skills(q: str = Query("")):
    orch = get_orchestrator()
    se = getattr(orch, '_skill_engine', None)
    if se is None:
        return {"enabled": False, "skills": []}
    if not q:
        return {"enabled": True, "skills": [], "total": 0}
    skills = se.registry.find(q)
    return {"enabled": True, "skills": [s.to_dict() for s in skills], "total": len(skills)}


@router.post("/skills/suggest")
async def suggest_skill(body: dict):
    orch = get_orchestrator()
    se = getattr(orch, '_skill_engine', None)
    if se is None:
        return {"success": False, "error": "Skill engine not configured"}
    task = body.get("task", "")
    if not task:
        return {"success": False, "error": "task is required"}
    result = await se.suggest(task)
    return result


@router.post("/skills/execute")
async def execute_skill(body: dict, request: Request):
    from modules.auth import request_identity
    orch = get_orchestrator()
    se = getattr(orch, '_skill_engine', None)
    if se is None:
        return {"success": False, "error": "Skill engine not configured"}
    skill_id = body.get("skill_id", "")
    params = body.get("params", {})
    if not skill_id:
        return {"success": False, "error": "skill_id is required"}
    identity = request_identity(request).to_dict()
    result = await se.execute(skill_id, params, context={"identity": identity, "session_id": body.get("session_id")})
    return result.to_dict()


@router.get("/alerts")
def list_alerts(
    source: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    acknowledged: Optional[bool] = Query(None),
    limit: int = Query(100),
):
    orch = get_orchestrator()
    am = getattr(orch, '_alert_manager', None)
    if am is None:
        return {"enabled": False, "alerts": []}
    from sentinel.core.alerting import AlertSeverity
    sev = AlertSeverity(severity) if severity else None
    alerts = am.list(source=source, severity=sev, acknowledged=acknowledged, limit=limit)
    return {"alerts": alerts, "stats": am.stats()}


@router.post("/alerts/acknowledge")
def acknowledge_alert(body: dict):
    orch = get_orchestrator()
    am = getattr(orch, '_alert_manager', None)
    if am is None:
        return {"acknowledged": 0}
    alert_id = body.get("alert_id", "")
    if alert_id:
        ok = am.acknowledge(alert_id)
        return {"acknowledged": 1 if ok else 0}
    source = body.get("source")
    count = am.acknowledge_all(source=source)
    return {"acknowledged": count}


@router.post("/alerts/check")
async def check_alerts():
    orch = get_orchestrator()
    am = getattr(orch, '_alert_manager', None)
    if am is None:
        return {"checked": False}
    count = am.check_all()
    return {"checked": True, "new_alerts": count, "stats": am.stats()}


@router.post("/alerts/clear")
def clear_alerts(acknowledged_only: bool = Query(True)):
    orch = get_orchestrator()
    am = getattr(orch, '_alert_manager', None)
    if am is None:
        return {"cleared": 0}
    count = am.clear(acknowledged_only=acknowledged_only)
    return {"cleared": count}


# ── Knowledge Base endpoints ────────────────────────────────────────────────

def _get_kb(orch):
    return getattr(orch, '_knowledge_base', None) or getattr(orch._tool_gateway, '_knowledge_base', None)


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
def kb_add(body: dict):
    orch = get_orchestrator()
    kb = _get_kb(orch)
    if kb is None:
        return {"enabled": False}
    text = body.get("text", "")
    if not text:
        return {"error": "text is required"}
    metadata = {"source": body.get("source", "api")}
    doc_id = body.get("doc_id")
    did = kb.add_text(text, metadata=metadata, doc_id=doc_id)
    return {"doc_id": did, "status": "added"}


@router.post("/kb/add-file")
async def kb_add_file(body: dict):
    orch = get_orchestrator()
    kb = _get_kb(orch)
    if kb is None:
        return {"enabled": False}
    path = body.get("path", "")
    if not path:
        return {"error": "path is required"}
    if not os.path.exists(path):
        return {"error": f"File not found: {path}"}
    doc_id = kb.add_file(path)
    return {"doc_id": doc_id, "path": path, "status": "added"}


@router.get("/kb/list")
def kb_list():
    orch = get_orchestrator()
    kb = _get_kb(orch)
    if kb is None:
        return {"enabled": False, "documents": []}
    docs = kb.list_documents()
    return {
        "documents": [
            {"doc_id": d.doc_id, "source": d.source, "chunks": d.chunks, "created_at": d.created_at}
            for d in docs
        ],
        "total": len(docs),
    }


@router.delete("/kb/{doc_id}")
def kb_delete(doc_id: str):
    orch = get_orchestrator()
    kb = _get_kb(orch)
    if kb is None:
        return {"enabled": False}
    removed = kb.delete(doc_id)
    return {"doc_id": doc_id, "removed": removed}


@router.post("/kb/clear")
def kb_clear():
    orch = get_orchestrator()
    kb = _get_kb(orch)
    if kb is None:
        return {"enabled": False}
    count = kb.clear()
    return {"cleared": count}


@router.get("/kb/stats")
def kb_stats():
    orch = get_orchestrator()
    kb = _get_kb(orch)
    if kb is None:
        return {"enabled": False}
    return {"enabled": True, **kb.stats()}


@router.post("/kb/rebuild")
def kb_rebuild():
    orch = get_orchestrator()
    kb = _get_kb(orch)
    if kb is None:
        return {"enabled": False}
    kb.rebuild()
    return {"status": "rebuilding"}


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
    return getattr(orch, '_file_pipeline', None) or getattr(orch._tool_gateway, '_file_pipeline', None)


@router.post("/pipeline/ingest")
def pipeline_ingest(body: dict):
    orch = get_orchestrator()
    fp = _get_pipeline(orch)
    if fp is None:
        return {"enabled": False}
    path = body.get("path", "")
    if not path:
        return {"error": "path is required"}
    try:
        result = fp.ingest(
            path,
            recursive=body.get("recursive", True),
            repo=body.get("repo", False),
        )
        return result.to_dict()
    except Exception as e:
        return {"error": str(e), "files_processed": 0, "files_failed": 1}


@router.get("/pipeline/status")
def pipeline_status():
    orch = get_orchestrator()
    fp = _get_pipeline(orch)
    if fp is None:
        return {"enabled": False}
    return {"enabled": True, **fp.stats()}


@router.post("/pipeline/reset-stats")
def pipeline_reset_stats():
    orch = get_orchestrator()
    fp = _get_pipeline(orch)
    if fp is None:
        return {"enabled": False}
    fp.reset_stats()
    return {"status": "reset"}


# ── Web Browsing endpoints ──────────────────────────────────────────────────

def _get_web(orch):
    return getattr(orch, '_web_browsing', None) or getattr(orch._tool_gateway, '_web_browsing', None)


@router.post("/web/navigate")
def web_navigate(body: dict):
    orch = get_orchestrator()
    wb = _get_web(orch)
    if wb is None:
        return {"enabled": False}
    url = body.get("url", "")
    if not url:
        return {"error": "url is required"}
    timeout = body.get("timeout", 15)
    result = wb.navigate(url, timeout=timeout)
    return result.to_dict()


@router.post("/web/extract")
def web_extract(body: dict):
    orch = get_orchestrator()
    wb = _get_web(orch)
    if wb is None:
        return {"enabled": False}
    url = body.get("url", "")
    if not url:
        return {"error": "url is required"}
    timeout = body.get("timeout", 15)
    text = wb.extract_text(url, timeout=timeout)
    return {"url": url, "text": text, "length": len(text)}


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
    return getattr(orch, '_hardening', None) or getattr(orch._tool_gateway, '_hardening', None)


@router.get("/hardening/config")
def hardening_config():
    orch = get_orchestrator()
    h = _get_hardening(orch)
    if h is None:
        return {"enabled": False}
    return {"enabled": True, **h.stats()}


@router.put("/hardening/config")
def hardening_update_config(body: dict):
    orch = get_orchestrator()
    h = _get_hardening(orch)
    if h is None:
        return {"enabled": False}
    settable = {}
    for key in ("default_timeout_seconds", "default_circuit_breaker_threshold",
                 "default_circuit_breaker_cooldown", "default_retry_jitter"):
        if key in body:
            settable[key] = body[key]
    if settable:
        h.update_config(**settable)
    return {"updated": settable}


@router.put("/hardening/tool-override/{tool_id}")
def hardening_tool_override(tool_id: str, body: dict):
    orch = get_orchestrator()
    h = _get_hardening(orch)
    if h is None:
        return {"enabled": False}
    overrides = {}
    for key in ("timeout_seconds", "circuit_breaker_threshold",
                 "circuit_breaker_cooldown", "retry_jitter"):
        if key in body:
            overrides[key] = body[key]
    if overrides:
        h.set_tool_override(tool_id, **overrides)
    return {"tool_id": tool_id, "overrides": overrides}


@router.delete("/hardening/tool-override/{tool_id}")
def hardening_remove_override(tool_id: str):
    orch = get_orchestrator()
    h = _get_hardening(orch)
    if h is None:
        return {"enabled": False}
    removed = h.remove_tool_override(tool_id)
    return {"tool_id": tool_id, "removed": removed}


@router.post("/hardening/circuit-breaker/reset")
def hardening_reset_circuits(body: dict = {}):
    orch = get_orchestrator()
    h = _get_hardening(orch)
    if h is None:
        return {"enabled": False}
    tool_id = body.get("tool_id", "")
    count = h.circuit_breaker.reset(tool_id if tool_id else None)
    return {"reset": tool_id or "all", "circuits_reset": count}


@router.get("/hardening/health")
def hardening_health():
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
def profile_get(user_id: str = ""):
    pm = _get_profile_mgr()
    if pm is None:
        return {"enabled": False}
    uid = user_id or "local-user"
    profile = pm.get_profile(uid)
    if profile is None:
        profile = pm.get_or_create_profile(uid)
    data = profile.to_dict()
    data["preferences"] = pm.get_all_preferences(uid)
    return data


@router.patch("/profile")
def profile_update(body: dict):
    pm = _get_profile_mgr()
    if pm is None:
        return {"enabled": False}
    uid = body.get("user_id", "local-user")
    pm.get_or_create_profile(uid)
    allowed = {"username", "display_name", "avatar", "theme", "timezone", "locale", "bio", "tags"}
    updates = {k: v for k, v in body.items() if k in allowed}
    profile = pm.update_profile(uid, **updates)
    return profile.to_dict()


@router.get("/profile/preferences")
def profile_preferences(user_id: str = ""):
    pm = _get_profile_mgr()
    if pm is None:
        return {"enabled": False}
    uid = user_id or "local-user"
    prefs = pm.get_all_preferences(uid)
    return {"preferences": prefs, "count": len(prefs)}


@router.put("/profile/preferences")
def profile_set_preference(body: dict):
    pm = _get_profile_mgr()
    if pm is None:
        return {"enabled": False}
    uid = body.get("user_id", "local-user")
    key = body.get("key", "")
    value = body.get("value")
    if not key:
        return {"error": "key is required"}
    pm.get_or_create_profile(uid)
    pm.set_preference(uid, key, value)
    return {"key": key, "value": value, "status": "set"}


@router.delete("/profile/preferences")
def profile_delete_preference(key: str = "", user_id: str = ""):
    pm = _get_profile_mgr()
    if pm is None:
        return {"enabled": False}
    uid = user_id or "local-user"
    if not key:
        return {"error": "key is required"}
    pm.delete_preference(uid, key)
    return {"key": key, "status": "deleted"}


@router.get("/profile/history")
def profile_history(user_id: str = "", limit: int = 50):
    pm = _get_profile_mgr()
    if pm is None:
        return {"enabled": False}
    uid = user_id or "local-user"
    history = pm.get_profile_history(uid, limit=limit)
    return {"history": history, "count": len(history)}


@router.get("/profile/export")
def profile_export(user_id: str = ""):
    pm = _get_profile_mgr()
    if pm is None:
        return {"enabled": False}
    uid = user_id or "local-user"
    data = pm.export_profile(uid)
    return data


@router.post("/profile/import")
def profile_import(body: dict):
    pm = _get_profile_mgr()
    if pm is None:
        return {"enabled": False}
    uid = body.get("user_id", "local-user")
    result = pm.import_profile(uid, body)
    return result


@router.get("/profile/presets")
def profile_presets(user_id: str = ""):
    pm = _get_profile_mgr()
    if pm is None:
        return {"enabled": False}
    uid = user_id or "local-user"
    presets = pm.list_presets(uid)
    return {"presets": presets, "count": len(presets)}


@router.post("/profile/presets")
def profile_save_preset(body: dict):
    pm = _get_profile_mgr()
    if pm is None:
        return {"enabled": False}
    uid = body.get("user_id", "local-user")
    preset_name = body.get("preset_name", "")
    if not preset_name:
        return {"error": "preset_name is required"}
    ok = pm.save_preset(uid, preset_name, description=body.get("description", ""))
    if not ok:
        return {"error": f"Preset '{preset_name}' already exists"}
    return {"preset_name": preset_name, "status": "saved"}


@router.post("/profile/presets/apply")
def profile_apply_preset(body: dict):
    pm = _get_profile_mgr()
    if pm is None:
        return {"enabled": False}
    uid = body.get("user_id", "local-user")
    preset_name = body.get("preset_name", "")
    if not preset_name:
        return {"error": "preset_name is required"}
    result = pm.apply_preset(uid, preset_name)
    return result


@router.delete("/profile/presets")
def profile_delete_preset(body: dict):
    pm = _get_profile_mgr()
    if pm is None:
        return {"enabled": False}
    uid = body.get("user_id", "local-user")
    preset_name = body.get("preset_name", "")
    if not preset_name:
        return {"error": "preset_name is required"}
    pm.delete_preset(uid, preset_name)
    return {"preset_name": preset_name, "status": "deleted"}


@router.get("/profile/search")
def profile_search(query: str = "", limit: int = 20):
    pm = _get_profile_mgr()
    if pm is None:
        return {"enabled": False, "results": []}
    if not query:
        return {"error": "query is required", "results": []}
    results = pm.search_profiles(query, limit=limit)
    return {"results": results, "count": len(results)}
