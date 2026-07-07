import json
import os
from datetime import datetime
from enum import Enum
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

PERM_FILE = os.path.expanduser("~/.aivo_permissions.json")

class PermissionLevel(str, Enum):
    VIEW = "view"
    CONFIRM = "confirm"
    AUTO = "auto"
    ADMIN = "admin"

class ConfirmRequest(BaseModel):
    action_id: str
    approved: bool

PENDING_ACTIONS: dict = {}
EMERGENCY_STOP = False

DESTRUCTIVE_PATTERNS = [
    "rm ", "del ", "format", "shutdown", "reboot", "restart-computer",
    "stop-computer", "Remove-Item", "Clear-Content", "net user",
    "reg delete", "diskpart", "cleanmgr /sageset", "taskkill /f",
    "set-executionpolicy", "wevtutil cl", "cipher /w",
]

CRITICAL_PATHS = [
    "C:\\Windows\\System32", "C:\\Windows", "C:\\Program Files",
    os.path.expanduser("~\\AppData"),
]

def load_permissions() -> dict:
    defaults = {"level": "confirm", "allowlist": [], "blocklist": [], "auto_safe": True}
    if os.path.exists(PERM_FILE):
        with open(PERM_FILE) as f:
            return {**defaults, **json.load(f)}
    return defaults

def save_permissions(data: dict):
    with open(PERM_FILE, "w") as f:
        json.dump(data, f, indent=2)

def is_destructive(command: str) -> bool:
    cmd_lower = command.lower()
    for pattern in DESTRUCTIVE_PATTERNS:
        if pattern in cmd_lower:
            return True
    return False

def touches_critical_path(path: str) -> bool:
    for cp in CRITICAL_PATHS:
        if cp.lower() in path.lower():
            return True
    return False

def check_permission(action: str, command: str = "") -> dict:
    perms = load_permissions()
    level = perms["level"]

    if EMERGENCY_STOP:
        return {"allowed": False, "reason": "Emergency stop is active", "level": level}

    for blocked in perms.get("blocklist", []):
        if blocked.lower() in command.lower():
            return {"allowed": False, "reason": f"Command blocked by policy: {blocked}", "level": level}

    if level == "view":
        return {"allowed": False, "reason": "View mode: execution disabled", "level": level}

    is_dangerous = is_destructive(command) or touches_critical_path(command)

    if level == "admin":
        return {"allowed": True, "reason": "", "level": level}

    if level == "auto":
        if is_dangerous:
            return {"allowed": False, "reason": "Destructive action requires confirmation", "needs_confirm": True, "level": level}
        return {"allowed": True, "reason": "", "level": level}

    if level == "confirm":
        if is_dangerous:
            return {"allowed": False, "reason": "Destructive action requires confirmation", "needs_confirm": True, "level": level}
        return {"allowed": False, "reason": "Action requires confirmation", "needs_confirm": True, "level": level}

    return {"allowed": False, "reason": f"Unknown permission level: {level}", "level": level}

@router.get("/status")
def get_permission_status():
    perms = load_permissions()
    return {
        **perms,
        "emergency_stop": EMERGENCY_STOP,
        "pending_actions": len(PENDING_ACTIONS),
    }

@router.post("/level")
def set_permission_level(level: PermissionLevel):
    perms = load_permissions()
    perms["level"] = level.value
    save_permissions(perms)
    return {"status": "ok", "level": level.value}

@router.post("/emergency/{action}")
def emergency_action(action: str):
    global EMERGENCY_STOP
    if action == "stop":
        EMERGENCY_STOP = True
        PENDING_ACTIONS.clear()
        return {"status": "emergency_stop_activated"}
    elif action == "resume":
        EMERGENCY_STOP = False
        return {"status": "emergency_stop_deactivated"}
    raise HTTPException(400, "Use 'stop' or 'resume'")

@router.post("/confirm")
def confirm_action(req: ConfirmRequest):
    if req.action_id not in PENDING_ACTIONS:
        return {"status": "expired", "message": "Action expired or already handled"}
    action = PENDING_ACTIONS.pop(req.action_id)
    if req.approved:
        return {"status": "approved", "action": action}
    return {"status": "denied", "action": action}

@router.post("/blocklist")
def add_blocklist(pattern: str):
    perms = load_permissions()
    if pattern not in perms["blocklist"]:
        perms["blocklist"].append(pattern)
        save_permissions(perms)
    return {"status": "ok", "blocklist": perms["blocklist"]}

@router.delete("/blocklist/{item}")
def remove_blocklist(item: str):
    perms = load_permissions()
    perms["blocklist"] = [p for p in perms["blocklist"] if p != item]
    save_permissions(perms)
    return {"status": "ok", "blocklist": perms["blocklist"]}
