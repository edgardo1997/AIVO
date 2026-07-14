import dataclasses
import logging
import uuid
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from services.executor_service import ExecutorService, DESTRUCTIVE_PATTERNS

log = logging.getLogger("sentinel.executor")
router = APIRouter()

# Keep _svc for backward compatibility and for informative endpoints
_svc = ExecutorService()

class CommandRequest(BaseModel):
    command: str
    timeout: int = 30
    confirmed: bool = False
    action_id: str = ""

class LaunchRequest(BaseModel):
    app_name: str
    args: str = ""

def wire_dependencies(permissions_svc, audit_svc):
    _svc.set_permissions_service(permissions_svc)
    _svc.set_audit_service(audit_svc)
    # _svc.set_plugins_service omitted — plugins is a legacy module

def _identity_dict(request: Request) -> dict:
    identity = getattr(request.state, "identity", None)
    if identity is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return {
        "user_id": identity.user_id,
        "username": getattr(identity, "username", ""),
        "role": getattr(identity, "role", "user"),
        "level": identity.level,
        "is_authenticated": getattr(identity, "is_authenticated", False),
        "is_local": getattr(identity, "is_local", True),
    }

def _executor_result(result):
    from sentinel.core.tool import ToolResult
    if isinstance(result, ToolResult):
        if result.requires_confirmation:
            return {
                "needs_confirm": True,
                "action_id": (result.data or {}).get("action_id", ""),
                "reason": result.error or "Requires confirmation",
                "classification": (result.data or {}).get("classification", "unknown"),
            }
        if result.success:
            return result.data
        return {"stdout": "", "stderr": result.error or "Unknown error", "returncode": -1}
    return result

@router.post("/command")
async def run_command(req: CommandRequest, request: Request):
    from modules.sentinel_bridge import get_orchestrator
    from modules.audit import _svc as audit_svc
    orch = get_orchestrator()
    params = {
        "command": req.command,
        "timeout": req.timeout,
        "confirmed": req.confirmed,
        "action_id": req.action_id,
    }
    result = await orch.execute_direct(
        "executor.command", params,
        identity=_identity_dict(request),
    )
    if result.tool_result and result.tool_result.requires_confirmation:
        action_id = str(uuid.uuid4())
        classification = _svc.classify_command(req.command)
        from modules.permissions import _svc as perm_svc
        perm_svc.create_pending_action(action_id, {
            "command": req.command,
            "classification": classification,
            "timeout": req.timeout,
        })
        audit_svc.log_action("command_pending", req.command, "pending_confirmation")
        return {
            "needs_confirm": True,
            "action_id": action_id,
            "reason": result.tool_result.error or "Requires confirmation",
            "classification": classification,
        }
    return _executor_result(result.tool_result)
@router.post("/launch")
async def launch_app(req: LaunchRequest, request: Request):
    from modules.sentinel_bridge import get_orchestrator
    orch = get_orchestrator()
    result = await orch.execute_direct(
        "executor.launch", {"app_name": req.app_name, "args": req.args},
        identity=_identity_dict(request),
    )
    tool_result = result.tool_result
    if not tool_result or not tool_result.success:
        raise HTTPException(status_code=500, detail=(tool_result.error if tool_result else "Execution failed"))
    return tool_result.data


@router.post("/kill/{pid}")
async def kill_process(pid: int, request: Request):
    from modules.sentinel_bridge import get_orchestrator
    orch = get_orchestrator()
    result = await orch.execute_direct(
        "executor.kill", {"pid": pid},
        identity=_identity_dict(request),
    )
    tool_result = result.tool_result
    if not tool_result or not tool_result.success:
        detail = (tool_result.error or "Kill failed") if tool_result else "Kill failed"
        if "not found" in detail.lower():
            raise HTTPException(status_code=404, detail=detail)
        if "denied" in detail.lower() or "access" in detail.lower():
            raise HTTPException(status_code=403, detail=detail)
        raise HTTPException(status_code=500, detail=detail)
    return tool_result.data

@router.get("/which/{name}")
def which_app(name: str):
    return _svc.which_app(name)

@router.get("/apps")
def list_installed_apps():
    return _svc.list_installed_apps()

@router.get("/destructive-patterns")
def get_destructive_patterns():
    return _svc.get_destructive_patterns()
