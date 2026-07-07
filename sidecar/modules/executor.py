import subprocess
import shutil
import os
import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from .permissions import check_permission, PENDING_ACTIONS, DESTRUCTIVE_PATTERNS
from .audit import log_action
from .plugins import run_hook

router = APIRouter()

class CommandRequest(BaseModel):
    command: str
    timeout: int = 30
    confirmed: bool = False
    action_id: str = ""

class LaunchRequest(BaseModel):
    app_name: str
    args: str = ""

DESTRUCTIVE_DESCRIPTIONS = {
    "rm ": "Delete files/folders",
    "del ": "Delete files",
    "format": "Format disk",
    "shutdown": "Shut down system",
    "reboot": "Reboot system",
    "restart-computer": "Restart computer",
    "stop-computer": "Stop computer",
    "Remove-Item": "Remove files/folders",
    "Clear-Content": "Clear file content",
    "net user": "Modify user accounts",
    "reg delete": "Delete registry keys",
    "diskpart": "Disk partition operations",
    "taskkill /f": "Force kill processes",
}

def classify_command(cmd: str) -> str:
    cmd_lower = cmd.lower()
    for pattern, desc in DESTRUCTIVE_DESCRIPTIONS.items():
        if pattern in cmd_lower:
            return f"DESTRUCTIVE: {desc}"
    for safe in ["dir", "ls", "echo", "type", "find", "more", "help", "cd ", "pwd", "whoami", "ipconfig", "systeminfo", "tasklist", "netstat"]:
        if cmd_lower.startswith(safe):
            return "safe"
    return "unknown"

@router.post("/command")
def run_command(req: CommandRequest):
    classification = classify_command(req.command)

    # Plugin on_command hooks
    plugin_results = run_hook("on_command", command=req.command, classification=classification)
    for pr in plugin_results:
        if pr.get("result", {}).get("handled"):
            log_action("command_handled_by_plugin", f"{req.command} via {pr['plugin']}", "success")
            return {
                "stdout": pr["result"].get("stdout", ""),
                "stderr": pr["result"].get("stderr", ""),
                "returncode": pr["result"].get("returncode", 0),
                "classification": "plugin",
                "plugin": pr["plugin"],
                "handled": True,
            }

    if req.action_id and req.action_id in PENDING_ACTIONS:
        action = PENDING_ACTIONS.pop(req.action_id)
        if not req.confirmed:
            log_action("command_blocked", f"{req.command} (user denied)", "blocked")
            return {"stdout": "", "stderr": "Action was not confirmed", "returncode": -1}
    else:
        perm = check_permission("execute", req.command)
        if not perm["allowed"]:
            if perm.get("needs_confirm"):
                action_id = str(uuid.uuid4())
                PENDING_ACTIONS[action_id] = {
                    "command": req.command,
                    "classification": classification,
                    "timeout": req.timeout,
                }
                log_action("command_pending", req.command, "pending_confirmation")
                return {
                    "needs_confirm": True,
                    "action_id": action_id,
                    "reason": perm.get("reason", "Requires confirmation"),
                    "classification": classification,
                }
            log_action("command_blocked", f"{req.command} ({perm.get('reason', 'permission denied')})", "blocked")
            return {"stdout": "", "stderr": perm.get("reason", "Permission denied"), "returncode": -1}

    try:
        result = subprocess.run(
            req.command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=req.timeout,
        )
        log_action("command_executed", req.command, "success" if result.returncode == 0 else "error")
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
            "classification": classification,
        }
    except subprocess.TimeoutExpired:
        log_action("command_timeout", req.command, "timeout")
        return {"stdout": "", "stderr": "Command timed out", "returncode": -1}
    except Exception as e:
        log_action("command_error", req.command, "error")
        return {"stdout": "", "stderr": str(e), "returncode": -1}

@router.post("/launch")
def launch_app(req: LaunchRequest):
    # Plugin on_command hooks
    plugin_results = run_hook("on_command", command=f"launch {req.app_name}", classification="launch")
    for pr in plugin_results:
        if pr.get("result", {}).get("handled"):
            log_action("launch_handled_by_plugin", f"{req.app_name} via {pr['plugin']}", "success")
            return {"success": True, "plugin": pr["plugin"], "handled": True}

    perm = check_permission("launch", req.app_name)
    if not perm["allowed"]:
        raise HTTPException(403, perm.get("reason", "Permission denied"))
    try:
        app = shutil.which(req.app_name) or req.app_name
        subprocess.Popen([app] + (req.args.split() if req.args else []),
                         shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log_action("app_launched", f"{req.app_name} {req.args}", "success")
        return {"success": True, "message": f"Launched {req.app_name}"}
    except Exception as e:
        log_action("app_launch_error", f"{req.app_name}: {str(e)}", "error")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/kill/{pid}")
def kill_process(pid: int):
    perm = check_permission("kill", f"kill pid {pid}")
    if not perm["allowed"]:
        raise HTTPException(403, perm.get("reason", "Permission denied"))
    try:
        import psutil
        proc = psutil.Process(pid)
        proc.terminate()
        log_action("process_killed", f"PID {pid} ({proc.name()})", "success")
        return {"success": True, "message": f"Process {pid} terminated"}
    except Exception as e:
        log_action("process_kill_error", f"PID {pid}: {str(e)}", "error")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/which/{name}")
def which_app(name: str):
    path = shutil.which(name)
    return {"name": name, "path": path, "found": path is not None}

@router.get("/apps")
def list_installed_apps():
    paths = os.environ.get("PATH", "").split(os.pathsep)
    apps = set()
    for p in paths:
        if os.path.isdir(p):
            for f in os.listdir(p):
                if f.endswith(".exe") and not f.startswith("uninstall"):
                    apps.add(f.replace(".exe", ""))
    return sorted(apps)[:200]

@router.get("/destructive-patterns")
def get_destructive_patterns():
    return {"patterns": DESTRUCTIVE_PATTERNS}
