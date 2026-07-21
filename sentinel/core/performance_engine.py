import logging
from typing import Any, Dict, Optional

from sentinel.core.event_bus import EventBus
from sentinel.core.events import SentinelEvent
from sentinel.core import event_types
from sentinel.core import power_manager
from sentinel.core import gpu_manager

log = logging.getLogger(__name__)

_profile_to_gpu = {
    "performance": "gaming",
    "high_performance": "max_performance",
    "balanced": "default",
    "balanceado": "default",
    "power_saver": "power_saver",
    "powersaver": "power_saver",
    "ultimate": "max_performance",
}

PROFILE_MAP = {
    "balanced":        "381b4222-f694-41f0-9685-ff5bb260df2f",
    "balanceado":      "381b4222-f694-41f0-9685-ff5bb260df2f",
    "performance":     "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",
    "high_performance": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",
    "power_saver":     "e9a42b02-d5df-448d-aa00-03f14749eb61",
    "powersaver":      "e9a42b02-d5df-448d-aa00-03f14749eb61",
    "ultimate":        "e9a42b02-d5df-448d-aa00-03f14749eb61",
}


class PerformanceEngine:
    def __init__(self, event_bus: Optional[EventBus] = None):
        self._event_bus = event_bus
        self._enabled = False
        self._profiling = False
        self._profile = "balanced"

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def profiling(self) -> bool:
        return self._profiling

    @property
    def profile(self) -> str:
        return self._profile

    def status(self) -> Dict[str, Any]:
        plans = power_manager.list_plans()
        active_plan = plans.active_name if plans.success else ""
        return {
            "enabled": self._enabled,
            "profiling": self._profiling,
            "profile": self._profile,
            "active_power_plan": active_plan,
        }

    def set_profile(self, profile: str, session_id: str = "", request_id: str = "") -> Dict[str, Any]:
        old = self._profile
        self._profile = profile

        guid = PROFILE_MAP.get(profile.lower())
        results = {"profile": profile, "previous": old}
        if guid:
            pw_result = power_manager.set_active_plan(guid)
            if pw_result.success:
                results["power_plan"] = pw_result.active_name
                results["plan_guid"] = pw_result.active_guid
                log.info("Power plan set: %s (%s)", pw_result.active_name, pw_result.active_guid)
            else:
                results["power_plan_error"] = pw_result.error
                log.warning("Power plan failed: %s", pw_result.error)

        gpu_profile = _profile_to_gpu.get(profile.lower())
        if gpu_profile:
            gp_result = gpu_manager.set_gpu_profile(gpu_profile)
            if gp_result.success:
                results["gpu_profile"] = gpu_profile
                log.info("GPU profile set: %s", gpu_profile)
            else:
                results["gpu_profile_error"] = gp_result.error
                log.warning("GPU profile failed: %s", gp_result.error)

        self._emit(event_types.PERFORMANCE_PROFILE_APPLIED, session_id, request_id, details=results)
        return results

    def set_enabled(self, enabled: bool, session_id: str = "", request_id: str = "") -> Dict[str, Any]:
        self._enabled = enabled
        self._emit(event_types.PERFORMANCE_SETTINGS_CHANGED, session_id, request_id, details={"enabled": enabled})
        log.info("Performance engine %s", "enabled" if enabled else "disabled")
        return {"enabled": enabled}

    def start_profiling(self, session_id: str = "", request_id: str = "") -> Dict[str, Any]:
        if self._profiling:
            return {"profiling": True, "already": True}
        self._profiling = True
        self._emit(event_types.PERFORMANCE_PROFILING_STARTED, session_id, request_id)
        log.info("Performance profiling started")
        return {"profiling": True}

    def stop_profiling(self, session_id: str = "", request_id: str = "") -> Dict[str, Any]:
        if not self._profiling:
            return {"profiling": False, "already": True}
        self._profiling = False
        self._emit(event_types.PERFORMANCE_PROFILING_STOPPED, session_id, request_id)
        log.info("Performance profiling stopped")
        return {"profiling": False}

    def _emit(self, event_type: str, session_id: str, request_id: str, details: Optional[Dict] = None):
        if self._event_bus is None:
            return
        self._event_bus.emit(SentinelEvent.new(
            event_type=event_type,
            session_id=session_id or "system",
            request_id=request_id or "",
            component="performance_engine",
            details=details,
        ))
