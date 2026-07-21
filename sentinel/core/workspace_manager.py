import logging
from typing import Any, Dict, List, Optional
from sentinel.core.event_bus import EventBus
from sentinel.core.events import SentinelEvent
from sentinel.core import event_types

log = logging.getLogger(__name__)


class WorkspaceManager:
    def __init__(self, event_bus: Optional[EventBus] = None):
        self._event_bus = event_bus
        self._workspaces: Dict[str, Dict[str, Any]] = {}
        self._active = ""

    def list_workspaces(self) -> List[Dict[str, Any]]:
        return [{"id": wid, **w} for wid, w in self._workspaces.items()]

    def status(self) -> Dict[str, Any]:
        return {"workspaces": len(self._workspaces), "active": self._active}

    def create(self, workspace_id: str, path: str = "", session_id: str = "", request_id: str = "") -> Dict[str, Any]:
        if workspace_id in self._workspaces:
            return {"created": False, "error": "already exists"}
        self._workspaces[workspace_id] = {"path": path, "created_at": __import__("time").time()}
        self._emit(event_types.WORKSPACE_CREATED, session_id, request_id, details={"workspace_id": workspace_id, "path": path})
        log.info("Workspace created: %s", workspace_id)
        return {"created": True, "workspace_id": workspace_id}

    def open(self, workspace_id: str, session_id: str = "", request_id: str = "") -> Dict[str, Any]:
        if workspace_id not in self._workspaces:
            return {"opened": False, "error": "not found"}
        self._active = workspace_id
        self._emit(event_types.WORKSPACE_OPENED, session_id, request_id, details={"workspace_id": workspace_id})
        log.info("Workspace opened: %s", workspace_id)
        return {"opened": True, "workspace_id": workspace_id}

    def close(self, session_id: str = "", request_id: str = "") -> Dict[str, Any]:
        if not self._active:
            return {"closed": False, "error": "no active workspace"}
        wid = self._active
        self._active = ""
        self._emit(event_types.WORKSPACE_CLOSED, session_id, request_id, details={"workspace_id": wid})
        log.info("Workspace closed: %s", wid)
        return {"closed": True, "workspace_id": wid}

    def delete(self, workspace_id: str, session_id: str = "", request_id: str = "") -> Dict[str, Any]:
        if workspace_id not in self._workspaces:
            return {"deleted": False, "error": "not found"}
        if self._active == workspace_id:
            self._active = ""
        del self._workspaces[workspace_id]
        self._emit(event_types.WORKSPACE_DELETED, session_id, request_id, details={"workspace_id": workspace_id})
        log.info("Workspace deleted: %s", workspace_id)
        return {"deleted": True, "workspace_id": workspace_id}

    def _emit(self, event_type: str, session_id: str, request_id: str, details: Optional[Dict] = None):
        if self._event_bus is None:
            return
        self._event_bus.emit(SentinelEvent.new(
            event_type=event_type,
            session_id=session_id or "system",
            request_id=request_id or "",
            component="workspace_manager",
            details=details,
        ))
