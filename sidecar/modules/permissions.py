import logging
import threading
from typing import TYPE_CHECKING
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from enum import Enum

from services.permissions_service import PermissionsService
from modules.permissions_memory import PendingActionsDict, EmergencyStopFlag

if TYPE_CHECKING:
    from sentinel.core.operational_memory import MemoryBackend

log = logging.getLogger("sentinel.permissions")
router = APIRouter()

# Module-level state — encapsulated (not exported), owned by _svc
_pending_actions = PendingActionsDict()
_emergency_stop = EmergencyStopFlag()
_state_lock = threading.RLock()

# Service is the sole owner of pending actions + emergency stop state
_svc = PermissionsService(
    pending_actions=_pending_actions,
    emergency_stop=_emergency_stop,
    state_lock=_state_lock,
)


def set_memory_backend(memory: "MemoryBackend") -> None:
    """Bind OperationalMemory to the service's pending actions and emergency stop."""
    _pending_actions.set_memory(memory)
    _emergency_stop.set_memory(memory)
    log.info("OperationalMemory bound to permissions service")


class PermissionLevel(str, Enum):
    VIEW = "view"
    CONFIRM = "confirm"
    AUTO = "auto"
    ADMIN = "admin"


class ConfirmRequest(BaseModel):
    action_id: str
    approved: bool


class LevelRequest(BaseModel):
    level: PermissionLevel


@router.get("/status")
def get_permission_status(request: Request):
    from modules.auth import request_identity, require_level

    identity = request_identity(request)
    require_level(identity, "view")
    return _svc.get_status()


async def _execute_permission_tool(tool_id: str, params: dict, request: Request):
    from modules import get_execution_pipeline
    from modules.auth import request_identity

    identity = request_identity(request).to_dict()
    return await get_execution_pipeline().execute(tool_id, params, {"identity": identity}, source="api")


@router.post("/level")
async def set_permission_level(req: LevelRequest, request: Request):
    result = await _execute_permission_tool("permissions.set_level", {"level": req.level.value}, request)
    if not result.success:
        raise HTTPException(status_code=403, detail=result.error or "Permission level change denied")
    return result.data


@router.post("/emergency/{action}")
async def emergency_action(action: str, request: Request):
    result = await _execute_permission_tool("permissions.emergency", {"action": action}, request)
    if not result.success:
        raise HTTPException(status_code=403, detail=result.error or "Emergency action denied")
    return result.data


@router.post("/confirm")
async def confirm_action(req: ConfirmRequest, request: Request):
    result = await _execute_permission_tool(
        "permissions.confirm", {"action_id": req.action_id, "approved": req.approved}, request
    )
    if result.success:
        return {"status": "confirmed", "result": result.data}
    return {"status": "rejected", "error": result.error}


@router.post("/blocklist")
async def add_blocklist(pattern: str, request: Request):
    result = await _execute_permission_tool("permissions.blocklist_add", {"pattern": pattern}, request)
    if not result.success:
        raise HTTPException(status_code=403, detail=result.error or "Blocklist update denied")
    return result.data


@router.delete("/blocklist/{item}")
async def remove_blocklist(item: str, request: Request):
    result = await _execute_permission_tool("permissions.blocklist_remove", {"item": item}, request)
    if not result.success:
        raise HTTPException(status_code=403, detail=result.error or "Blocklist update denied")
    return result.data
