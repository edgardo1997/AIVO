import logging
from typing import Any, Dict, Optional
from sentinel.core.event_bus import EventBus
from sentinel.core.events import SentinelEvent
from sentinel.core import event_types
from sentinel.core import power_manager
from sentinel.core import gpu_manager

log = logging.getLogger(__name__)


class GamingMode:
    def __init__(self, event_bus: Optional[EventBus] = None):
        self._event_bus = event_bus
        self._enabled = False
        self._active_game = ""
        self._profile = "performance"

    def status(self) -> Dict[str, Any]:
        return {"enabled": self._enabled, "active_game": self._active_game, "profile": self._profile}

    def activate(self, game: str = "", session_id: str = "", request_id: str = "") -> Dict[str, Any]:
        self._enabled = True
        if game:
            self._active_game = game
        results = {"game": self._active_game, "actions": []}

        pw = power_manager.set_active_plan("ultimate")
        if pw.success:
            results["actions"].append(f"power_plan={pw.active_name}")
        else:
            results["power_plan_error"] = pw.error

        gp = gpu_manager.set_gpu_profile("gaming")
        if gp.success:
            results["actions"].append("gpu_profile=gaming")
        else:
            results["gpu_profile_error"] = gp.error

        self._emit(event_types.GAMING_MODE_ACTIVATED, session_id, request_id, details=results)
        log.info("Gaming mode activated (game=%s): %s", self._active_game, results["actions"])
        return self.status()

    def deactivate(self, session_id: str = "", request_id: str = "") -> Dict[str, Any]:
        self._enabled = False
        self._active_game = ""
        results = {"actions": []}

        pw = power_manager.set_active_plan("balanced")
        if pw.success:
            results["actions"].append(f"power_plan={pw.active_name}")
        else:
            results["power_plan_error"] = pw.error

        gp = gpu_manager.set_gpu_profile("default")
        if gp.success:
            results["actions"].append("gpu_profile=default")
        else:
            results["gpu_profile_error"] = gp.error

        self._emit(event_types.GAMING_MODE_DEACTIVATED, session_id, request_id, details=results)
        log.info("Gaming mode deactivated: %s", results["actions"])
        return self.status()

    def detect_game(self, game: str, session_id: str = "", request_id: str = "") -> Dict[str, Any]:
        self._active_game = game
        self._emit(event_types.GAMING_GAME_DETECTED, session_id, request_id, details={"game": game})
        log.info("Game detected: %s", game)
        return {"game": game}

    def set_profile(self, profile: str, session_id: str = "", request_id: str = "") -> Dict[str, Any]:
        old = self._profile
        self._profile = profile
        self._emit(event_types.GAMING_PROFILE_APPLIED, session_id, request_id, details={"from": old, "to": profile})
        log.info("Gaming profile: %s -> %s", old, profile)
        return {"profile": profile, "previous": old}

    def _emit(self, event_type: str, session_id: str, request_id: str, details: Optional[Dict] = None):
        if self._event_bus is None:
            return
        self._event_bus.emit(SentinelEvent.new(
            event_type=event_type,
            session_id=session_id or "system",
            request_id=request_id or "",
            component="gaming_mode",
            details=details,
        ))
