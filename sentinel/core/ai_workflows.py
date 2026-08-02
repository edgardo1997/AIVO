import asyncio
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
        self._workflows[wid] = {
            "name": name,
            "steps": steps,
            "status": "created",
            "current_step": 0,
            "result_data": [],
            "error": "",
            "resume_data": {},
        }
        self._emit(
            event_types.WORKFLOW_CREATED,
            session_id,
            request_id,
            details={"workflow_id": wid, "name": name, "steps": len(steps)},
        )
        log.info("Workflow created: %s (%s)", name, wid)
        return {"created": True, "workflow_id": wid, "name": name}

    def start(self, workflow_id: str, session_id: str = "", request_id: str = "") -> Dict[str, Any]:
        wf = self._workflows.get(workflow_id)
        if wf is None:
            return {"started": False, "error": "not found"}
        wf["status"] = "running"
        wf["current_step"] = 0
        wf["result_data"] = []
        wf["error"] = ""
        wf["resume_data"] = {}
        self._active = workflow_id
        self._emit(
            event_types.WORKFLOW_STARTED,
            session_id,
            request_id,
            details={"workflow_id": workflow_id, "name": wf["name"]},
        )
        log.info("Workflow started: %s", workflow_id)
        return {"started": True, "workflow_id": workflow_id}

    def execute_step(
        self, workflow_id: str, step_result: str = "", session_id: str = "", request_id: str = ""
    ) -> Dict[str, Any]:
        wf = self._workflows.get(workflow_id)
        if wf is None:
            return {"executed": False, "error": "not found"}
        step_index = wf["current_step"]
        steps = wf["steps"]
        if step_index >= len(steps):
            return {"executed": False, "error": "all steps completed"}
        step_name = steps[step_index]
        wf["current_step"] = step_index + 1
        wf.setdefault("result_data", []).append({"step": step_index, "name": step_name, "result": step_result})
        wf["resume_data"] = {"next_step": wf["current_step"]}
        self._emit(
            event_types.WORKFLOW_STEP_EXECUTED,
            session_id,
            request_id,
            details={"workflow_id": workflow_id, "step": step_index, "name": step_name, "result": step_result},
        )
        log.info("Workflow step %d/%d executed: %s", step_index + 1, len(steps), step_name)
        return {"executed": True, "step": step_index, "name": step_name, "steps_remaining": len(steps) - step_index - 1}

    def complete(self, workflow_id: str, session_id: str = "", request_id: str = "") -> Dict[str, Any]:
        wf = self._workflows.get(workflow_id)
        if wf is None:
            return {"completed": False, "error": "not found"}
        wf["status"] = "completed"
        wf["resume_data"] = {}
        if self._active == workflow_id:
            self._active = None
        self._emit(
            event_types.WORKFLOW_COMPLETED,
            session_id,
            request_id,
            details={"workflow_id": workflow_id, "name": wf["name"]},
        )
        log.info("Workflow completed: %s", workflow_id)
        return {"completed": True, "workflow_id": workflow_id}

    def delete(self, workflow_id: str, session_id: str = "", request_id: str = "") -> Dict[str, Any]:
        wf = self._workflows.pop(workflow_id, None)
        if wf is None:
            return {"deleted": False, "error": "not found"}
        if self._active == workflow_id:
            self._active = None
        self._emit(
            event_types.WORKFLOW_DELETED,
            session_id,
            request_id,
            details={"workflow_id": workflow_id, "name": wf.get("name", "")},
        )
        log.info("Workflow deleted: %s", workflow_id)
        return {"deleted": True, "workflow_id": workflow_id}

    def fail(self, workflow_id: str, error: str = "", session_id: str = "", request_id: str = "") -> Dict[str, Any]:
        wf = self._workflows.get(workflow_id)
        if wf is None:
            return {"failed": False, "error": "not found"}
        wf["status"] = "failed"
        wf["error"] = error
        wf["resume_data"] = {"next_step": wf.get("current_step", 0)}
        if self._active == workflow_id:
            self._active = None
        self._emit(
            event_types.WORKFLOW_FAILED, session_id, request_id, details={"workflow_id": workflow_id, "error": error}
        )
        log.error("Workflow failed: %s (%s)", workflow_id, error)
        return {"failed": True, "workflow_id": workflow_id, "error": error}

    def cancel(self, workflow_id: str, session_id: str = "", request_id: str = "") -> Dict[str, Any]:
        """Cancel a workflow without misrepresenting it as an execution failure."""
        wf = self._workflows.get(workflow_id)
        if wf is None:
            return {"cancelled": False, "error": "not found"}
        wf["status"] = "cancelled"
        wf["error"] = "cancelled"
        wf["resume_data"] = {"next_step": wf.get("current_step", 0)}
        if self._active == workflow_id:
            self._active = None
        self._emit(
            event_types.WORKFLOW_CANCELLED,
            session_id,
            request_id,
            details={"workflow_id": workflow_id, "name": wf["name"]},
        )
        log.info("Workflow cancelled: %s", workflow_id)
        return {"cancelled": True, "workflow_id": workflow_id}

    def _emit(self, event_type: str, session_id: str, request_id: str, details: Optional[Dict] = None):
        if self._event_bus is None:
            return
        event = SentinelEvent.new(
            event_type=event_type,
            session_id=session_id or "system",
            request_id=request_id or "",
            component="ai_workflows",
            details=details,
        )
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(self._event_bus.emit(event))
        else:
            loop.create_task(self._event_bus.emit(event))
