"""VS Code plugin — developer workflows through Sentinel commands.

Only reads the workspace and launches the editor; it never modifies project
files. All operations are best-effort and safe when VS Code is not present.
"""

import logging
import os
import shutil
import subprocess
from pathlib import Path

from sentinel.plugin_sdk import SentinelPlugin

logger = logging.getLogger(__name__)


def _code_binary() -> str:
    return shutil.which("code") or shutil.which("code.cmd") or "code"


def _run(args, cwd=None):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=15, cwd=cwd)
    except Exception:
        return None


def _detect_workspace() -> dict:
    # Best-effort: the most recently modified directory containing a .git or .code-workspace.
    candidates = []
    for root in (Path.home(), Path.cwd()):
        if not root.is_dir():
            continue
        try:
            for child in root.iterdir():
                if child.is_dir() and ((child / ".git").exists() or (child / ".code-workspace").exists()):
                    candidates.append((child.stat().st_mtime, str(child)))
        except Exception:
            logger.debug("Skipping inaccessible workspace root '%s'", root, exc_info=True)
            continue
    candidates.sort(reverse=True)
    return {"workspace": candidates[0][1] if candidates else None}


class VSCodePlugin(SentinelPlugin):
    def on_ready(self):
        return {"status": "ready", "commands": ["open project", "workspace", "git status", "run task"]}

    def on_command(self, command, **kwargs):
        text = str(command or "").lower()

        if "git status" in text or "status git" in text:
            self.require("filesystem.read")
            workspace = kwargs.get("workspace") or _detect_workspace().get("workspace")
            if not workspace:
                return {"handled": False, "note": "no workspace detected"}
            result = _run(["git", "status", "--short"], cwd=workspace)
            return {"handled": True, "action": "git_status", "workspace": workspace, "status": result.stdout if result else "git unavailable"}

        if "workspace" in text or "detect" in text:
            self.require("filesystem.read")
            return {"handled": True, "action": "detect_workspace", **_detect_workspace()}

        if "open" in text:
            self.require("application.launch")
            workspace = kwargs.get("path") or kwargs.get("workspace") or "."
            result = _run([_code_binary(), str(workspace)])
            return {"handled": True, "action": "open", "path": str(workspace), "launched": result is not None}

        if "run task" in text or "task" in text:
            self.require("application.launch")
            task = kwargs.get("task", "build")
            _run([_code_binary(), "--run-task", str(task)])
            return {"handled": True, "action": "run_task", "task": task}

        return {"handled": False}

    def tool_specs(self):
        return [
            {
                "id": "vscode.detect_workspace",
                "name": "Detect Workspace",
                "description": "Detecta el workspace de VS Code activo",
                "permissions": ["filesystem.read"],
            },
            {
                "id": "vscode.git_status",
                "name": "Git Status",
                "description": "Estado git del proyecto abierto",
                "permissions": ["filesystem.read"],
            },
        ]
