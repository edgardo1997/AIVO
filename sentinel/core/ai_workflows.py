import logging
import uuid
from typing import Any, Dict, List, Optional
from sentinel.core.event_bus import EventBus
from sentinel.core.events import SentinelEvent
from sentinel.core import event_types

log = logging.getLogger(__name__)


class AIWorkflows:
    def __init__(self, event_bus: Optional[EventBus] = None):
        self._event_bus = event_bus
        self._workflows: Dict[str, Dict[str, Any]] = {}
        self._active: Optional[str] = None

    def status(self) -> Dict[str, Any]:
        return {"workflows": len(self._workflows), "active": self._active}

    def list_workflows(self) -> List[Dict[str, Any]]:
        return [{"id": wid, **w} for wid, w in self._workflows.items()]

    def create(self, name: str, steps: List[str], session_id: str = "", request_id: str = "") -> Dict[str, Any]:
        wid = uuid.uuid4().hex[:12]
        self._workflows[wid] = {"name": name, "steps": steps, "status": "created", "current_step": 0}
        self._emit(event_types.WORKFLOW_CREATED, session_id, request_id, details={"workflow_id": wid, "name": name, "steps": len(steps)})
        log.info("Workflow created: %s (%s)", name, wid)
        return {"created": True, "workflow_id": wid, "name": name}

    def start(self, workflow_id: str, session_id: str = "", request_id: str = "") -> Dict[str, Any]:
        wf = self._workflows.get(workflow_id)
        if wf is None:
            return {"started": False, "error": "not found"}
        wf["status"] = "running"
        wf["current_step"] = 0
        self._active = workflow_id
        self._emit(event_types.WORKFLOW_STARTED, session_id, request_id, details={"workflow_id": workflow_id, "name": wf["name"]})
        log.info("Workflow started: %s", workflow_id)
        return {"started": True, "workflow_id": workflow_id}

    def execute_step(self, workflow_id: str, step_result: str = "", session_id: str = "", request_id: str = "") -> Dict[str, Any]:
        wf = self._workflows.get(workflow_id)
        if wf is None:
            return {"executed": False, "error": "not found"}
        step_index = wf["current_step"]
        steps = wf["steps"]
        if step_index >= len(steps):
            return {"executed": False, "error": "all steps completed"}
        step_name = steps[step_index]
        wf["current_step"] = step_index + 1
        self._emit(event_types.WORKFLOW_STEP_EXECUTED, session_id, request_id, details={"workflow_id": workflow_id, "step": step_index, "name": step_name, "result": step_result})
        log.info("Workflow step %d/%d executed: %s", step_index + 1, len(steps), step_name)
        return {"executed": True, "step": step_index, "name": step_name, "steps_remaining": len(steps) - step_index - 1}

    def complete(self, workflow_id: str, session_id: str = "", request_id: str = "") -> Dict[str, Any]:
        wf = self._workflows.get(workflow_id)
        if wf is None:
            return {"completed": False, "error": "not found"}
        wf["status"] = "completed"
        if self._active == workflow_id:
            self._active = None
        self._emit(event_types.WORKFLOW_COMPLETED, session_id, request_id, details={"workflow_id": workflow_id, "name": wf["name"]})
        log.info("Workflow completed: %s", workflow_id)
        return {"completed": True, "workflow_id": workflow_id}

    def fail(self, workflow_id: str, error: str = "", session_id: str = "", request_id: str = "") -> Dict[str, Any]:
        wf = self._workflows.get(workflow_id)
        if wf is None:
            return {"failed": False, "error": "not found"}
        wf["status"] = "failed"
        wf["error"] = error
        if self._active == workflow_id:
            self._active = None
        self._emit(event_types.WORKFLOW_FAILED, session_id, request_id, details={"workflow_id": workflow_id, "error": error})
        log.error("Workflow failed: %s (%s)", workflow_id, error)
        return {"failed": True, "workflow_id": workflow_id, "error": error}

    def _emit(self, event_type: str, session_id: str, request_id: str, details: Optional[Dict] = None):
        if self._event_bus is None:
            return
        self._event_bus.emit(SentinelEvent.new(
            event_type=event_type,
            session_id=session_id or "system",
            request_id=request_id or "",
            component="ai_workflows",
            details=details,
        ))
