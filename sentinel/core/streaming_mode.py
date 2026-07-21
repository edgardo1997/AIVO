import logging
from typing import Any, Dict, Optional
from sentinel.core.event_bus import EventBus
from sentinel.core.events import SentinelEvent
from sentinel.core import event_types
from sentinel.core import power_manager
from sentinel.core import gpu_manager

log = logging.getLogger(__name__)


class StreamingMode:
    def __init__(self, event_bus: Optional[EventBus] = None):
        self._event_bus = event_bus
        self._enabled = False
        self._platform = ""
        self._stream_active = False
        self._stream_key_configured = False

    def status(self) -> Dict[str, Any]:
        return {"enabled": self._enabled, "platform": self._platform, "stream_active": self._stream_active, "stream_key_configured": self._stream_key_configured}

    def activate(self, platform: str = "", session_id: str = "", request_id: str = "") -> Dict[str, Any]:
        self._enabled = True
        if platform:
            self._platform = platform
        results = {"platform": self._platform, "actions": []}

        pw = power_manager.set_active_plan("balanced")
        if pw.success:
            results["actions"].append(f"power_plan={pw.active_name}")
        else:
            results["power_plan_error"] = pw.error

        gp = gpu_manager.set_gpu_profile("quiet")
        if gp.success:
            results["actions"].append("gpu_profile=quiet")
        else:
            results["gpu_profile_error"] = gp.error

        self._emit(event_types.STREAMING_MODE_ACTIVATED, session_id, request_id, details=results)
        log.info("Streaming mode activated (platform=%s): %s", self._platform, results["actions"])
        return self.status()

    def deactivate(self, session_id: str = "", request_id: str = "") -> Dict[str, Any]:
        self._enabled = False
        self._stream_active = False
        results = {"actions": []}

        pw = power_manager.set_active_plan("balanced")
        if pw.success:
            results["actions"].append(f"power_plan={pw.active_name}")

        gp = gpu_manager.set_gpu_profile("default")
        if gp.success:
            results["actions"].append("gpu_profile=default")

        self._emit(event_types.STREAMING_MODE_DEACTIVATED, session_id, request_id, details=results)
        log.info("Streaming mode deactivated: %s", results["actions"])
        return self.status()

    def start_stream(self, session_id: str = "", request_id: str = "") -> Dict[str, Any]:
        if self._stream_active:
            return {"stream_active": True, "already": True}
        self._stream_active = True
        self._emit(event_types.STREAMING_STREAM_STARTED, session_id, request_id)
        log.info("Stream started")
        return {"stream_active": True}

    def stop_stream(self, session_id: str = "", request_id: str = "") -> Dict[str, Any]:
        if not self._stream_active:
            return {"stream_active": False, "already": True}
        self._stream_active = False
        self._emit(event_types.STREAMING_STREAM_STOPPED, session_id, request_id)
        log.info("Stream stopped")
        return {"stream_active": False}

    def _emit(self, event_type: str, session_id: str, request_id: str, details: Optional[Dict] = None):
        if self._event_bus is None:
            return
        self._event_bus.emit(SentinelEvent.new(
            event_type=event_type,
            session_id=session_id or "system",
            request_id=request_id or "",
            component="streaming_mode",
            details=details,
        ))
