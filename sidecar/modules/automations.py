"""Automation & workflow persistence for Sentinel Desktop (FASE 11 GTM).

Wraps the shared in-memory :class:`AutomationEngine` and :class:`AIWorkflows`
singletons with SQLite-backed persistence plus export/import, so user
automation survives restarts and can be shared with the community (the
"depender de Sentinel" PLG loop described in ``docs/FASE_11_GTM.md``).

Triggers already persist in their own module (``modules.triggers``); this
module covers automation rules and AI workflows, which were in-memory only.
"""

import json
import logging
import threading
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request

from repositories.database import DatabaseManager
from modules import get_automation_engine, get_ai_workflows
from modules.product_metrics_probe import record_automation_created

log = logging.getLogger("sentinel.automations")
router = APIRouter()

_db: Optional[DatabaseManager] = None
_state_lock = threading.RLock()
_loaded_database_id: Optional[int] = None


class _RequestBinding:
    __slots__ = ("session_id", "identity_hash")

    def __init__(self, session_id: str = "", identity_hash: str = "") -> None:
        self.session_id = session_id
        self.identity_hash = identity_hash


_mod_request_ctx: ContextVar[Optional[_RequestBinding]] = ContextVar(
    "sentinel_automation_request_ctx", default=None
)


def get_engine():
    return get_automation_engine()


def get_workflows():
    return get_ai_workflows()


# ── Persistence ─────────────────────────────────────────────────────────


def _rule_binding():
    """Return the owning session+identity binding for newly created rules.

    Automations inherit the security context of the session/identity that
    created them so they can be re-validated (fail-closed) after a restart
    instead of silently re-using an expired context.
    """
    session_id = getattr(_mod_request_ctx, "session_id", "") or ""
    identity_hash = getattr(_mod_request_ctx, "identity_hash", "") or ""
    return session_id, identity_hash


def _save_rule(
    rule_id: str,
    condition: str,
    action: str,
    enabled: bool = True,
    trigger_count: int = 0,
    session_id: str = "",
    identity_hash: str = "",
) -> None:
    if not _db:
        return
    now = datetime.now(timezone.utc).isoformat()
    if not session_id and not identity_hash:
        session_id, identity_hash = _rule_binding()
    _db.execute(
        """INSERT OR REPLACE INTO automation_rules
           (rule_id, condition, action, enabled, trigger_count, owner_session_id, owner_identity_hash, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (rule_id, condition, action, 1 if enabled else 0, trigger_count, session_id, identity_hash, now),
    )
    _db.commit()


def _delete_rule_db(rule_id: str) -> None:
    if not _db:
        return
    _db.execute("DELETE FROM automation_rules WHERE rule_id = ?", (rule_id,))
    _db.commit()


def _save_workflow(
    workflow_id: str,
    name: str,
    steps: List[str],
    status: str = "created",
    current_step: int = 0,
    result_data: Optional[List[Dict[str, Any]]] = None,
    error: str = "",
    resume_data: Optional[Dict[str, Any]] = None,
    session_id: str = "",
    identity_hash: str = "",
) -> None:
    if not _db:
        return
    now = datetime.now(timezone.utc).isoformat()
    if not session_id and not identity_hash:
        session_id, identity_hash = _rule_binding()
    _db.execute(
        """INSERT OR REPLACE INTO ai_workflows
           (workflow_id, name, steps, status, current_step, result_data, error, resume_data,
            owner_session_id, owner_identity_hash, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            workflow_id,
            name,
            json.dumps(steps, ensure_ascii=False),
            status,
            int(current_step or 0),
            json.dumps(result_data or [], ensure_ascii=False),
            error or "",
            json.dumps(resume_data or {}, ensure_ascii=False),
            session_id,
            identity_hash,
            now,
        ),
    )
    _db.commit()


def _save_workflow_state(workflow_id: str) -> None:
    """Persist the current in-memory state of a workflow (status/current_step)."""
    if not _db:
        return
    workflows = get_workflows()
    wf = workflows._workflows.get(workflow_id)
    if not wf:
        return
    binding_session, binding_hash = "", ""
    if _db:
        row = _db.fetchone("SELECT owner_session_id, owner_identity_hash FROM ai_workflows WHERE workflow_id = ?", (workflow_id,))
        if row:
            binding_session = row.get("owner_session_id") or ""
            binding_hash = row.get("owner_identity_hash") or ""
    _save_workflow(
        workflow_id,
        wf.get("name", ""),
        wf.get("steps", []),
        wf.get("status", "created"),
        wf.get("current_step", 0),
        wf.get("result_data", []),
        wf.get("error", ""),
        wf.get("resume_data", {}),
        binding_session,
        binding_hash,
    )


def _save_workflow_state_with_binding(workflow_id: str, session_id: str, identity_hash: str) -> None:
    """Persist the in-memory state of a workflow using an explicit binding."""
    if not _db:
        return
    workflows = get_workflows()
    wf = workflows._workflows.get(workflow_id)
    if not wf:
        return
    _save_workflow(
        workflow_id,
        wf.get("name", ""),
        wf.get("steps", []),
        wf.get("status", "created"),
        wf.get("current_step", 0),
        wf.get("result_data", []),
        wf.get("error", ""),
        wf.get("resume_data", {}),
        session_id,
        identity_hash,
    )


def _binding_authorized(rule_id: str, session_id: str = "", request_id: str = "") -> bool:
    """Fail-closed: a bound automation may only fire when the current context
    re-validates its owning session/identity binding."""
    rule = get_engine()._rules.get(rule_id, {})
    owner_session = rule.get("owner_session_id", "")
    owner_hash = rule.get("owner_identity_hash", "")
    if not owner_session and not owner_hash:
        return True
    ctx = _mod_request_ctx.get()
    ctx_hash = ctx.identity_hash if ctx else ""
    ctx_session = ctx.session_id if ctx else (session_id or "")
    if ctx_hash and owner_hash:
        return ctx_hash == owner_hash
    if owner_session:
        return bool(ctx_session) and ctx_session == owner_session
    return False


def _delete_workflow_db(workflow_id: str) -> None:
    if not _db:
        return
    _db.execute("DELETE FROM ai_workflows WHERE workflow_id = ?", (workflow_id,))
    _db.commit()


def _restore_rule(
    rule_id: str,
    condition: str,
    action: str,
    enabled: bool,
    trigger_count: int,
    session_id: str = "",
    identity_hash: str = "",
) -> None:
    get_engine()._rules[rule_id] = {
        "condition": condition,
        "action": action,
        "enabled": bool(enabled),
        "trigger_count": int(trigger_count or 0),
    }
    if session_id or identity_hash:
        get_engine()._rules[rule_id].update(
            {"owner_session_id": session_id, "owner_identity_hash": identity_hash, "revalidation_required": False}
        )


def _restore_workflow(
    workflow_id: str,
    name: str,
    steps: List[str],
    status: str,
    current_step: int,
    result_data: Optional[List[Dict[str, Any]]] = None,
    error: str = "",
    resume_data: Optional[Dict[str, Any]] = None,
    session_id: str = "",
    identity_hash: str = "",
) -> None:
    get_workflows()._workflows[workflow_id] = {
        "name": name,
        "steps": steps,
        "status": status or "created",
        "current_step": int(current_step or 0),
        "result_data": result_data or [],
        "error": error or "",
        "resume_data": resume_data or {},
    }
    if session_id or identity_hash:
        get_workflows()._workflows[workflow_id].update(
            {"owner_session_id": session_id, "owner_identity_hash": identity_hash, "revalidation_required": False}
        )


def _load_from_db() -> None:
    if not _db:
        return
    for row in _db.fetchall("SELECT * FROM automation_rules"):
        try:
            _restore_rule(
                row["rule_id"],
                row.get("condition", ""),
                row.get("action", ""),
                bool(row.get("enabled", 1)),
                row.get("trigger_count", 0),
                row.get("owner_session_id", "") or "",
                row.get("owner_identity_hash", "") or "",
            )
        except Exception as e:
            log.error("Failed to load automation rule '%s': %s", row.get("rule_id"), e)
    for row in _db.fetchall("SELECT * FROM ai_workflows"):
        try:
            steps = json.loads(row.get("steps", "[]"))
            result_data = json.loads(row.get("result_data", "[]"))
            resume_data = json.loads(row.get("resume_data", "{}"))
            _restore_workflow(
                row["workflow_id"],
                row.get("name", ""),
                steps if isinstance(steps, list) else [],
                row.get("status", "created"),
                row.get("current_step", 0),
                result_data if isinstance(result_data, list) else [],
                row.get("error", ""),
                resume_data if isinstance(resume_data, dict) else {},
                row.get("owner_session_id", "") or "",
                row.get("owner_identity_hash", "") or "",
            )
        except Exception as e:
            log.error("Failed to load workflow '%s': %s", row.get("workflow_id"), e)
    log.info(
        "Loaded %d automation rules and %d workflows from database",
        len(get_engine()._rules),
        len(get_workflows()._workflows),
    )


# ── Engine hooks ────────────────────────────────────────────────────────


def _wrap_workflow_transitions() -> None:
    """Persist workflow state after every transition."""
    workflows = get_workflows()

    transitions = (
        ("start", "started"),
        ("execute_step", "executed"),
        ("complete", "completed"),
        ("fail", "failed"),
        ("cancel", "cancelled"),
    )
    for method_name, result_key in transitions:
        if getattr(workflows, f"_sentinel_persist_{method_name}", False):
            continue
        orig = getattr(workflows, method_name)

        def make_wrapped(orig_fn, key):
            def wrapped(workflow_id: str, *args, **kwargs) -> Dict[str, Any]:
                result = orig_fn(workflow_id, *args, **kwargs)
                if result.get(key):
                    _save_workflow_state(workflow_id)
                return result

            return wrapped

        setattr(workflows, method_name, make_wrapped(orig, result_key))
        setattr(workflows, f"_sentinel_persist_{method_name}", True)


def _wrap_engine_for_persistence() -> None:
    engine = get_engine()
    workflows = get_workflows()

    orig_add = engine.add_rule

    def wrapped_add(rule_id: str, condition: str, action: str, session_id: str = "", request_id: str = "") -> Dict[str, Any]:
        result = orig_add(rule_id, condition, action, session_id=session_id, request_id=request_id)
        if result.get("added"):
            bind_session, bind_hash = _rule_binding()
            if session_id:
                bind_session = session_id or bind_session
            engine._rules[rule_id].update(
                {"owner_session_id": bind_session, "owner_identity_hash": bind_hash, "revalidation_required": False}
            )
            rule = engine._rules.get(rule_id, {})
            _save_rule(rule_id, condition, action, rule.get("enabled", True), rule.get("trigger_count", 0), bind_session, bind_hash)
            record_automation_created("automation_rule", rule_id)
        return result

    engine.add_rule = wrapped_add

    orig_remove = engine.remove_rule

    def wrapped_remove(rule_id: str, session_id: str = "", request_id: str = "") -> Dict[str, Any]:
        result = orig_remove(rule_id, session_id=session_id, request_id=request_id)
        if result.get("removed"):
            _delete_rule_db(rule_id)
        return result

    engine.remove_rule = wrapped_remove

    orig_trigger = engine.trigger_rule

    def wrapped_trigger(rule_id: str, session_id: str = "", request_id: str = "") -> Dict[str, Any]:
        rule = engine._rules.get(rule_id, {})
        owner_session = rule.get("owner_session_id", "")
        owner_hash = rule.get("owner_identity_hash", "")
        result = orig_trigger(rule_id, session_id=session_id, request_id=request_id)
        if result.get("triggered"):
            # Fail-closed revalidation: an automation bound to an owner must
            # only fire when the current execution context re-validates that
            # binding. After a restart the context is empty, so bound rules
            # refuse to trigger instead of silently re-using expired identity.
            if (owner_session or owner_hash) and not _binding_authorized(rule_id, session_id, request_id):
                engine._rules[rule_id]["trigger_count"] = max(0, engine._rules[rule_id].get("trigger_count", 1) - 1)
                return {"triggered": False, "revalidation_required": True, "rule_id": rule_id}
            rule = engine._rules.get(rule_id, {})
            _save_rule(
                rule_id,
                rule.get("condition", ""),
                rule.get("action", ""),
                rule.get("enabled", True),
                rule.get("trigger_count", 0),
                owner_session,
                owner_hash,
            )
        return result

    engine.trigger_rule = wrapped_trigger

    orig_create = workflows.create

    def wrapped_create(name: str, steps: List[str], session_id: str = "", request_id: str = "") -> Dict[str, Any]:
        result = orig_create(name, steps, session_id=session_id, request_id=request_id)
        if result.get("created"):
            bind_session, bind_hash = _rule_binding()
            if session_id:
                bind_session = session_id or bind_session
            workflows._workflows[result["workflow_id"]].update(
                {"owner_session_id": bind_session, "owner_identity_hash": bind_hash, "revalidation_required": False}
            )
            _save_workflow_state_with_binding(result["workflow_id"], bind_session, bind_hash)
            record_automation_created("workflow", result["workflow_id"])
        return result

    workflows.create = wrapped_create

    orig_delete = workflows.delete

    def wrapped_delete(workflow_id: str, session_id: str = "", request_id: str = "") -> Dict[str, Any]:
        result = orig_delete(workflow_id, session_id=session_id, request_id=request_id)
        if result.get("deleted"):
            _delete_workflow_db(workflow_id)
        return result

    workflows.delete = wrapped_delete

    _wrap_workflow_transitions()


def wire_dependencies(db: DatabaseManager) -> None:
    global _db, _loaded_database_id
    with _state_lock:
        _db = db
        if _loaded_database_id != id(db):
            _load_from_db()
            _loaded_database_id = id(db)


def ensure_wired() -> None:
    with _state_lock:
        engine = get_engine()
        if not getattr(engine, "_sentinel_automations_wired", False):
            _wrap_engine_for_persistence()
            engine._sentinel_automations_wired = True


# ── API helpers ─────────────────────────────────────────────────────────


def _list_payload() -> Dict[str, Any]:
    ensure_wired()
    rules = get_engine().list_rules()
    workflows = get_workflows().list_workflows()
    return {
        "automation_rules": rules,
        "workflows": workflows,
        "total_rules": len(rules),
        "total_workflows": len(workflows),
    }


def _export_payload() -> Dict[str, Any]:
    ensure_wired()
    return {
        "format": "sentinel-automations",
        "version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "automation_rules": [
            {
                "rule_id": r["id"],
                "condition": r.get("condition", ""),
                "action": r.get("action", ""),
                "enabled": r.get("enabled", True),
            }
            for r in get_engine().list_rules()
        ],
        "workflows": [
            {"workflow_id": w["id"], "name": w.get("name", ""), "steps": w.get("steps", [])}
            for w in get_workflows().list_workflows()
        ],
    }


def _import_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    ensure_wired()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Import payload must be an object")
    rules_in = payload.get("automation_rules") or []
    workflows_in = payload.get("workflows") or []
    if not isinstance(rules_in, list) or not isinstance(workflows_in, list):
        raise HTTPException(status_code=400, detail="automation_rules and workflows must be arrays")

    imported_rules = 0
    skipped_rules = 0
    for entry in rules_in:
        if not isinstance(entry, dict) or not entry.get("rule_id"):
            skipped_rules += 1
            continue
        rule_id = str(entry["rule_id"])
        if rule_id in get_engine()._rules:
            skipped_rules += 1
            continue
        get_engine().add_rule(
            rule_id,
            str(entry.get("condition", "")),
            str(entry.get("action", "")),
        )
        imported_rules += 1

    imported_workflows = 0
    skipped_workflows = 0
    for entry in workflows_in:
        if not isinstance(entry, dict) or not entry.get("workflow_id"):
            skipped_workflows += 1
            continue
        wid = str(entry["workflow_id"])
        if wid in get_workflows()._workflows:
            skipped_workflows += 1
            continue
        name = str(entry.get("name", ""))
        steps = entry.get("steps") if isinstance(entry.get("steps"), list) else []
        _restore_workflow(wid, name, [str(s) for s in steps], "created", 0)
        _save_workflow(wid, name, [str(s) for s in steps])
        record_automation_created("workflow", wid)
        imported_workflows += 1

    return {
        "imported_rules": imported_rules,
        "skipped_rules": skipped_rules,
        "imported_workflows": imported_workflows,
        "skipped_workflows": skipped_workflows,
    }


# ── API endpoints ───────────────────────────────────────────────────────


async def _pipeline_tool(tool_id: str, params: Dict[str, Any], request: Request) -> Dict[str, Any]:
    from modules import get_execution_pipeline
    from modules.auth import request_identity

    identity = request_identity(request).to_dict()
    _mod_request_ctx.set(_RequestBinding(session_id=identity.get("session_id") or "", identity_hash=identity.get("identity_hash") or ""))
    result = await get_execution_pipeline().execute(tool_id, params, {"identity": identity}, source="api")
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error or f"{tool_id} failed")
    return result.data or {}


@router.get("/automations")
def list_automations():
    return _list_payload()


@router.post("/automations", status_code=201)
async def create_automation(body: dict, request: Request):
    ensure_wired()
    rule_id = str(body.get("rule_id", "")).strip()
    if not rule_id:
        raise HTTPException(status_code=400, detail="rule_id is required")
    condition = str(body.get("condition", ""))
    action = str(body.get("action", ""))
    data = await _pipeline_tool(
        "automation.rules.add",
        {"rule_id": rule_id, "condition": condition, "action": action},
        request,
    )
    if not data.get("added"):
        raise HTTPException(status_code=409, detail=f"Automation rule '{rule_id}' already exists")
    return {"status": "created", "rule_id": rule_id, "result": data}


@router.delete("/automations/{rule_id}")
async def delete_automation(rule_id: str, request: Request):
    ensure_wired()
    data = await _pipeline_tool("automation.rules.remove", {"rule_id": rule_id}, request)
    if not data.get("removed"):
        raise HTTPException(status_code=404, detail=f"Automation rule '{rule_id}' not found")
    return {"status": "deleted", "rule_id": rule_id}


@router.post("/workflows", status_code=201)
async def create_workflow(body: dict, request: Request):
    ensure_wired()
    name = str(body.get("name", "")).strip()
    steps = body.get("steps") if isinstance(body.get("steps"), list) else []
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    steps = [str(s) for s in steps]
    data = await _pipeline_tool("workflow.create", {"name": name, "steps": steps}, request)
    if not data.get("created"):
        raise HTTPException(status_code=400, detail="Workflow creation failed")
    return {"status": "created", "workflow_id": data["workflow_id"], "name": name}


@router.delete("/workflows/{workflow_id}")
async def delete_workflow(workflow_id: str, request: Request):
    ensure_wired()
    data = await _pipeline_tool("workflow.delete", {"workflow_id": workflow_id}, request)
    if not data.get("deleted"):
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found")
    return {"status": "deleted", "workflow_id": workflow_id}


@router.get("/automations/export")
def export_automations():
    return _export_payload()


@router.post("/automations/import")
async def import_automations(body: dict, request: Request):
    ensure_wired()
    return await _pipeline_tool("automation.import", {"payload": body}, request)
