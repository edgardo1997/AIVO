import logging
import threading
from typing import TYPE_CHECKING
from fastapi import APIRouter, HTTPException
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
_state_lock = threading.Lock()

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
def get_permission_status():
    return _svc.get_status()


@router.post("/level")
def set_permission_level(req: LevelRequest):
    return _svc.set_level(req.level.value)


@router.post("/emergency/{action}")
def emergency_action(action: str):
    return _svc.emergency(action)


@router.post("/confirm")
def confirm_action(req: ConfirmRequest):
    return _svc.confirm_action(req.action_id, req.approved)


@router.post("/blocklist")
def add_blocklist(pattern: str):
    return _svc.add_blocklist(pattern)


@router.delete("/blocklist/{item}")
def remove_blocklist(item: str):
    return _svc.remove_blocklist(item)
