"""Conservative activation state machine with no runtime connection."""

from enum import Enum

from .control import ControlledActivationControl


class ActivationState(str, Enum):
    DISABLED = "DISABLED"
    LEGACY_ONLY = "LEGACY_ONLY"
    CANARY_ACTIVE = "CANARY_ACTIVE"
    ROLLBACK_ACTIVE = "ROLLBACK_ACTIVE"
    PAUSED = "PAUSED"


class ControlledRuntimeActivation:
    def __init__(self, control: ControlledActivationControl) -> None:
        self.control = control
        self.state = ActivationState.LEGACY_ONLY if control.enabled else ActivationState.DISABLED

    def start(self) -> bool:
        if not self.control.enabled or not self.control.canary_enabled or self.control.traffic_percentage <= 0:
            return False
        self.state = ActivationState.CANARY_ACTIVE
        return True

    def pause(self) -> None:
        if self.state is ActivationState.CANARY_ACTIVE:
            self.state = ActivationState.PAUSED

    def resume(self) -> bool:
        if self.state is not ActivationState.PAUSED:
            return False
        return self.start()

    def activate_rollback(self) -> None:
        if self.control.enabled:
            self.state = ActivationState.ROLLBACK_ACTIVE
