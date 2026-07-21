"""SentinelEvent model — standard event for Sentinel's Live Activity system."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import uuid


@dataclass
class SentinelEvent:
    event_id: str
    event_type: str
    timestamp: float
    session_id: str
    request_id: str
    parent_event_id: Optional[str] = None
    component: str = ""
    status: str = ""
    priority: str = "normal"
    progress: Optional[int] = None
    tool: Optional[str] = None
    message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    duration: Optional[float] = None

    @classmethod
    def new(
        cls,
        event_type: str,
        session_id: str,
        request_id: str,
        *,
        component: str = "",
        status: str = "",
        priority: str = "normal",
        progress: Optional[int] = None,
        tool: Optional[str] = None,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        duration: Optional[float] = None,
        parent_event_id: Optional[str] = None,
    ) -> "SentinelEvent":
        return cls(
            event_id=uuid.uuid4().hex,
            event_type=event_type,
            timestamp=datetime.now(timezone.utc).timestamp(),
            session_id=session_id,
            request_id=request_id,
            parent_event_id=parent_event_id,
            component=component,
            status=status,
            priority=priority,
            progress=progress,
            tool=tool,
            message=message,
            details=details,
            duration=duration,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "request_id": self.request_id,
            "parent_event_id": self.parent_event_id,
            "component": self.component,
            "status": self.status,
            "priority": self.priority,
            "progress": self.progress,
            "tool": self.tool,
            "message": self.message,
            "details": self.details,
            "duration": self.duration,
        }
