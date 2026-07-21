import logging
from typing import Any, Dict, List, Optional
from sentinel.core.event_bus import EventBus
from sentinel.core.events import SentinelEvent
from sentinel.core import event_types
from sentinel.core import power_manager

log = logging.getLogger(__name__)


class DeveloperMode:
    def __init__(self, event_bus: Optional[EventBus] = None):
        self._event_bus = event_bus
        self._enabled = False
        self._project_path = ""
        self._env_vars: Dict[str, str] = {}
        self._tools_enabled: List[str] = []

    def status(self) -> Dict[str, Any]:
        return {"enabled": self._enabled, "project_path": self._project_path, "env_vars": dict(self._env_vars), "tools_enabled": list(self._tools_enabled)}

    def activate(self, session_id: str = "", request_id: str = "") -> Dict[str, Any]:
        self._enabled = True
        results = {"actions": []}
        pw = power_manager.set_active_plan("balanced")
        if pw.success:
            results["actions"].append(f"power_plan={pw.active_name}")
        self._emit(event_types.DEVELOPER_MODE_ACTIVATED, session_id, request_id, details=results)
        log.info("Developer mode activated: %s", results["actions"])
        return self.status()

    def deactivate(self, session_id: str = "", request_id: str = "") -> Dict[str, Any]:
        self._enabled = False
        self._project_path = ""
        self._emit(event_types.DEVELOPER_MODE_DEACTIVATED, session_id, request_id)
        log.info("Developer mode deactivated")
        return self.status()

    def set_project(self, path: str, session_id: str = "", request_id: str = "") -> Dict[str, Any]:
        old = self._project_path
        self._project_path = path
        self._emit(event_types.DEVELOPER_PROJECT_SET, session_id, request_id, details={"path": path, "previous": old})
        log.info("Dev project set: %s", path)
        return {"project_path": path, "previous": old}

    def update_env(self, key: str, value: str, session_id: str = "", request_id: str = "") -> Dict[str, Any]:
        self._env_vars[key] = value
        self._emit(event_types.DEVELOPER_ENV_UPDATED, session_id, request_id, details={"key": key, "value": "***" if "key" in key.lower() or "secret" in key.lower() else value})
        log.info("Dev env updated: %s", key)
        return {"key": key, "set": True}

    def _emit(self, event_type: str, session_id: str, request_id: str, details: Optional[Dict] = None):
        if self._event_bus is None:
            return
        self._event_bus.emit(SentinelEvent.new(
            event_type=event_type,
            session_id=session_id or "system",
            request_id=request_id or "",
            component="developer_mode",
            details=details,
        ))
