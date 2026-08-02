"""Automation plugin — custom workflows, triggers and schedules.

Listens for task completions and re-emits them as automation triggers so the
host can chain follow-up actions. Includes a small registry of user-defined
workflows stored inside the plugin directory (filesystem.read only).
"""

import json
import os
from pathlib import Path

from sentinel.plugin_sdk import SentinelPlugin


class AutomationPlugin(SentinelPlugin):
    def on_ready(self):
        return {"status": "ready", "workflows": len(self._workflows())}

    def _workflows_path(self) -> Path:
        base = os.environ.get("SENTINEL_PLUGIN_DIR", str(Path.home() / ".aivo" / "plugins"))
        return Path(base) / "automation" / "workflows.json"

    def _workflows(self) -> dict:
        path = self._workflows_path()
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def on_event(self, event):
        if event.type in ("task.completed", "task.failed"):
            workflows = self._workflows()
            task_name = str(event.payload.get("task", "")).lower()
            matched = [wf for wf in workflows.values() if task_name in str(wf.get("when", "")).lower()]
            self.emit("automation.triggered", {"task": event.payload.get("task"), "ok": event.type == "task.completed", "workflows": len(matched)})
            return {"handled": True, "matched_workflows": len(matched)}
        if event.type == "automation.triggered":
            return {"handled": True, "relay": True}
        return {"handled": False}

    def on_command(self, command, **kwargs):
        text = str(command or "").lower()
        if "workflow" in text and "list" in text:
            self.require("filesystem.read")
            return {"handled": True, "action": "list_workflows", "workflows": list(self._workflows().keys())}
        return {"handled": False}

    def tool_specs(self):
        return [
            {
                "id": "automation.workflows",
                "name": "List Workflows",
                "description": "Lista los workflows de automatización definidos",
                "permissions": ["filesystem.read"],
            }
        ]
