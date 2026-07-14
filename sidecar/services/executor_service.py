import logging
import os
import re
import shlex
import shutil
import subprocess
from typing import Any, Dict, Optional

from sentinel.core.tool import Tool, ToolResult, ToolSpec, ToolStatus

log = logging.getLogger("sentinel.executor_service")

from sentinel.policies.loader import load_or_default, PolicyStore

SHELL_METACHARS = re.compile(r'[&|;`$%@()\[\]{}<>]')
ALLOWED_SAFE_CMDS = {
    "dir", "ls", "echo", "type", "find", "more", "help", "cd", "pwd",
    "whoami", "ipconfig", "systeminfo", "tasklist", "netstat", "ver",
    "date", "time", "cls", "clear", "tree", "set", "path", "chcp",
}


def _load_destructive_patterns():
    data = load_or_default(
        "destructive_patterns.yaml",
        default_factory=lambda: {"destructive_patterns": []},
    )
    return data.get("destructive_patterns", [])


DESTRUCTIVE_PATTERNS = _load_destructive_patterns()


def _reload_patterns():
    global DESTRUCTIVE_PATTERNS
    DESTRUCTIVE_PATTERNS = _load_destructive_patterns()


PolicyStore.get_instance().on_reload(_reload_patterns)

EXECUTOR_COMMAND_SPEC = ToolSpec(
    id="executor.command",
    name="Execute Command",
    description="Execute a system command with safety validation",
    version="0.1.0",
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Command to execute"},
            "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30},
            "confirmed": {"type": "boolean", "description": "User confirmed", "default": False},
            "action_id": {"type": "string", "description": "Confirmation action ID", "default": ""},
        },
        "required": ["command"],
    },
    required_permissions=["executor.command"],
    timeout_seconds=60,
    category="executor",
)

EXECUTOR_LAUNCH_SPEC = ToolSpec(
    id="executor.launch",
    name="Launch Application",
    description="Launch an application by name or path",
    version="0.1.0",
    parameters={
        "type": "object",
        "properties": {
            "app_name": {"type": "string", "description": "Application name or path"},
            "args": {"type": "string", "description": "Command-line arguments", "default": ""},
        },
        "required": ["app_name"],
    },
    required_permissions=["executor.launch"],
    timeout_seconds=15,
    category="executor",
)

EXECUTOR_KILL_SPEC = ToolSpec(
    id="executor.kill",
    name="Kill Process",
    description="Terminate a process by PID",
    version="0.1.0",
    parameters={
        "type": "object",
        "properties": {
            "pid": {"type": "integer", "description": "Process ID"},
        },
        "required": ["pid"],
    },
    required_permissions=["executor.kill"],
    timeout_seconds=10,
    category="executor",
)

EXECUTOR_RESTART_SPEC = ToolSpec(
    id="executor.restart",
    name="Restart Process",
    description="Restart a process that was previously killed",
    version="0.1.0",
    parameters={
        "type": "object",
        "properties": {
            "process_name": {"type": "string", "description": "Process name or path to restart"},
            "args": {"type": "string", "description": "Command-line arguments", "default": ""},
        },
        "required": ["process_name"],
    },
    required_permissions=["executor.launch"],
    timeout_seconds=15,
    category="executor",
)


class ExecutorService(Tool):
    def __init__(self, permissions_service=None, audit_service=None, plugins_service=None, guardian=None):
        super().__init__()
        self._perm = permissions_service
        self._audit = audit_service
        self._plugins = plugins_service
        self._guardian = guardian

    def spec(self) -> ToolSpec:
        return EXECUTOR_COMMAND_SPEC

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        command = params.get("command", "")
        timeout = params.get("timeout", 30)
        confirmed = params.get("confirmed", False)
        action_id = params.get("action_id", "")
        if not command:
            return ToolResult.fail(error="command is required", tool_id="executor.command")

        try:
            if self._guardian and self._is_file_operation(command):
                path = self._extract_path(command)
                if path:
                    valid = self._guardian.validate_write(path, context.get("identity") or context.get("auth"))
                    if not valid.allowed:
                        return ToolResult.fail(
                            error=f"File path blocked by policy: {valid.reason}",
                            tool_id="executor.command",
                        )

            result = self.execute_sync(command, timeout, confirmed, action_id)
            if result.get("needs_confirm"):
                tr = ToolResult.needs_confirm(
                    reason=result.get("reason", "Requires confirmation"),
                    tool_id="executor.command",
                    policy_id="permission_level",
                )
                tr.data = {
                    "action_id": result.get("action_id", ""),
                    "classification": result.get("classification", ""),
                }
                return tr
            return ToolResult.ok(data=result, tool_id="executor.command")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="executor.command")

    def set_permissions_service(self, svc):
        self._perm = svc

    def set_audit_service(self, svc):
        self._audit = svc

    def set_plugins_service(self, svc):
        self._plugins = svc

    # --- Tool sub-interface for launch ---

    def spec_launch(self) -> ToolSpec:
        return EXECUTOR_LAUNCH_SPEC

    async def execute_launch(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            result = self.launch_app(params["app_name"], params.get("args", ""))
            return ToolResult.ok(data=result, tool_id="executor.launch")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="executor.launch")

    def spec_kill(self) -> ToolSpec:
        return EXECUTOR_KILL_SPEC

    async def execute_kill(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            result = self.kill_process(params["pid"])
            return ToolResult.ok(data=result, tool_id="executor.kill")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="executor.kill")

    def spec_restart(self) -> ToolSpec:
        return EXECUTOR_RESTART_SPEC

    async def execute_restart(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            result = self.restart_process(params["process_name"], params.get("args", ""))
            return ToolResult.ok(data=result, tool_id="executor.restart")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="executor.restart")

    def validate_command(self, cmd: str) -> str:
        from fastapi import HTTPException
        if not cmd or not cmd.strip():
            raise HTTPException(400, "Command cannot be empty")
        if len(cmd) > 8192:
            raise HTTPException(400, "Command too long")
        cmd_stripped = cmd.strip()
        first_token = cmd_stripped.split(None, 1)[0].lower() if cmd_stripped else ""
        is_allowed_builtin = first_token in ALLOWED_SAFE_CMDS
        has_metachars = bool(SHELL_METACHARS.search(cmd_stripped))
        if has_metachars:
            log.warning("Blocked shell metacharacters in command: %s", cmd_stripped[:100])
            raise HTTPException(403, "Command blocked: shell chaining, expansion, and redirection are not allowed")
        return cmd_stripped

    def classify_command(self, cmd: str) -> str:
        cmd_lower = cmd.lower()
        for pattern in DESTRUCTIVE_PATTERNS:
            if pattern.lower() in cmd_lower:
                return f"DESTRUCTIVE: {pattern.strip()}"
        first_word = cmd.split(None, 1)[0].lower() if cmd.strip() else ""
        if first_word in ALLOWED_SAFE_CMDS or shutil.which(first_word):
            return "safe"
        return "unknown"

    def execute_sync(self, command: str, timeout: int = 30, confirmed: bool = False,
                action_id: str = "") -> dict:
        from fastapi import HTTPException
        safe_cmd = self.validate_command(command)
        classification = self.classify_command(safe_cmd)
        result = self._run_plugin_hooks(safe_cmd, classification)
        if result:
            return result

        if action_id and action_id in (self._perm.pending_actions if self._perm else {}):
            self._perm.pending_actions.pop(action_id)
            if not confirmed:
                self._log_action("command_blocked", f"{safe_cmd} (user denied)", "blocked")
                return {"stdout": "", "stderr": "Action was not confirmed", "returncode": -1}

        try:
            result = self._exec_safe(safe_cmd, timeout=timeout)
            self._log_action("command_executed", safe_cmd, "success" if result.returncode == 0 else "error")
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "classification": classification,
            }
        except subprocess.TimeoutExpired:
            self._log_action("command_timeout", safe_cmd, "timeout")
            return {"stdout": "", "stderr": "Command timed out", "returncode": -1}
        except Exception as e:
            self._log_action("command_error", safe_cmd, "error")
            return {"stdout": "", "stderr": str(e), "returncode": -1}

    def _run_plugin_hooks(self, command: str, classification: str) -> dict | None:
        if not self._plugins:
            return None
        try:
            plugin_results = self._plugins.run_hook("on_command", command=command, classification=classification)
            for pr in plugin_results:
                if pr.get("result", {}).get("handled"):
                    self._log_action("command_handled_by_plugin", f"{command} via {pr['plugin']}", "success")
                    return {
                        "stdout": pr["result"].get("stdout", ""),
                        "stderr": pr["result"].get("stderr", ""),
                        "returncode": pr["result"].get("returncode", 0),
                        "classification": "plugin",
                        "plugin": pr["plugin"],
                        "handled": True,
                    }
        except Exception as e:
            log.warning("Plugin hook error: %s", e)
        return None

    def _log_action(self, action: str, details: str, status: str):
        if self._audit:
            self._audit.log_action(action, details, status)

    def _exec_safe(self, cmd: str, timeout: int = 30) -> subprocess.CompletedProcess:
        try:
            args = shlex.split(cmd, posix=False)
        except ValueError:
            args = None
        if args and args[0].lower() in ALLOWED_SAFE_CMDS:
            return self._run_with_timeout(["cmd.exe", "/c", cmd], timeout)
        if args:
            executable = args[0] if os.path.isfile(args[0]) else shutil.which(args[0])
            if executable:
                return self._run_with_timeout([executable, *args[1:]], timeout)
        raise HTTPException(403, "Command blocked: executable is not installed or explicitly resolvable")

    def _run_with_timeout(self, cmd_args: list, timeout: int) -> subprocess.CompletedProcess:
        proc = subprocess.Popen(cmd_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            return subprocess.CompletedProcess(proc.args, proc.returncode, stdout, stderr)
        except subprocess.TimeoutExpired:
            self._kill_process_tree(proc.pid)
            stdout, stderr = proc.communicate()
            raise subprocess.TimeoutExpired(proc.args, timeout, stdout, stderr)

    def _kill_process_tree(self, pid: int):
        try:
            import psutil
            parent = psutil.Process(pid)
            for child in parent.children(recursive=True):
                try:
                    child.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            parent.kill()
        except (ImportError, psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    def launch_app(self, app_name: str, args: str = "") -> dict:
        from fastapi import HTTPException
        app_name = app_name.strip()
        if not app_name:
            raise HTTPException(400, "app_name cannot be empty")
        if ".." in app_name or "/" in app_name or "\\" in app_name:
            raise HTTPException(400, "Invalid app_name: path traversal detected")

        if self._plugins:
            plugin_results = self._plugins.run_hook("on_command", command=f"launch {app_name}", classification="launch")
            for pr in plugin_results:
                if pr.get("result", {}).get("handled"):
                    self._log_action("launch_handled_by_plugin", f"{app_name} via {pr['plugin']}", "success")
                    return {"success": True, "plugin": pr["plugin"], "handled": True}

        try:
            app_path = shutil.which(app_name) or app_name
            parsed_args = shlex.split(args, posix=False) if args else []
            subprocess.Popen([app_path, *parsed_args], shell=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._log_action("app_launched", f"{app_name} {args}", "success")
            return {"success": True, "message": f"Launched {app_name}"}
        except Exception as e:
            self._log_action("app_launch_error", f"{app_name}: {str(e)}", "error")
            raise HTTPException(status_code=500, detail=str(e))

    def kill_process(self, pid: int) -> dict:
        from fastapi import HTTPException
        if pid <= 0 or pid > 999999:
            raise HTTPException(400, "Invalid PID")
        try:
            import psutil
            proc = psutil.Process(pid)
            proc_name = proc.name()
            try:
                cmdline = proc.cmdline()
            except (psutil.AccessDenied, psutil.ZombieProcess):
                cmdline = [proc_name]
            proc.terminate()
            self._log_action("process_killed", f"PID {pid} ({proc_name})", "success")
            return {
                "success": True, "message": f"Process {pid} terminated",
                "pid": pid, "process_name": proc_name, "args": " ".join(cmdline[1:]) if len(cmdline) > 1 else "",
            }
        except psutil.NoSuchProcess:
            raise HTTPException(404, f"Process {pid} not found")
        except psutil.AccessDenied:
            raise HTTPException(403, f"Access denied to terminate process {pid}")
        except Exception as e:
            self._log_action("process_kill_error", f"PID {pid}: {str(e)}", "error")
            raise HTTPException(status_code=500, detail=str(e))

    def restart_process(self, process_name: str, args: str = "") -> dict:
        from fastapi import HTTPException
        if not process_name:
            raise HTTPException(400, "process_name cannot be empty")
        try:
            app_path = shutil.which(process_name) or process_name
            parsed_args = shlex.split(args, posix=False) if args else []
            subprocess.Popen([app_path, *parsed_args], shell=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._log_action("process_restarted", f"{process_name} {args}", "success")
            return {"success": True, "message": f"Restarted {process_name}"}
        except Exception as e:
            self._log_action("process_restart_error", f"{process_name}: {str(e)}", "error")
            raise HTTPException(status_code=500, detail=str(e))

    def which_app(self, name: str) -> dict:
        from fastapi import HTTPException
        if not name or "/" in name or "\\" in name:
            raise HTTPException(400, "Invalid app name")
        path = shutil.which(name)
        return {"name": name, "path": path, "found": path is not None}

    def list_installed_apps(self) -> list:
        paths = os.environ.get("PATH", "").split(os.pathsep)
        apps = set()
        for p in paths:
            if os.path.isdir(p):
                for f in os.listdir(p):
                    if f.endswith(".exe") and not f.startswith("uninstall"):
                        apps.add(f.replace(".exe", ""))
        return sorted(apps)[:200]

    def get_destructive_patterns(self) -> dict:
        return {"patterns": DESTRUCTIVE_PATTERNS}

    def _is_file_operation(self, command: str) -> bool:
        file_keywords = {"rm ", "del ", "remove-item", "clear-content", "copy ",
                         "move ", "ren ", "rename-item", "erase", "rd ", "rmdir"}
        lower = command.strip().lower()
        for pattern in DESTRUCTIVE_PATTERNS:
            if any(kw in pattern.lower() for kw in file_keywords):
                if pattern.lower() in lower:
                    return True
        return False

    def _extract_path(self, command: str) -> Optional[str]:
        parts = command.strip().split(None, 2)
        if len(parts) >= 2:
            candidate = parts[-1].strip("\"'")
            if os.path.isabs(candidate) or candidate.startswith(".") or candidate.startswith("~"):
                return candidate
        return None
