"""Feature and lifecycle state for replay validation."""

import os
from enum import Enum


RUNTIME_REPLAY_VALIDATION_ENABLED = False
_RUNTIME_REPLAY_ENV = "RUNTIME_REPLAY_VALIDATION_ENABLED"


class ReplayValidationState(str, Enum):
    DISABLED = "DISABLED"
    READY = "READY"
    RUNNING = "RUNNING"


class ReplayValidationControl:
    def __init__(
        self,
        *,
        enabled: bool | None = None,
        environ: dict[str, str] | None = None,
    ) -> None:
        source = os.environ if environ is None else environ
        if enabled is None:
            raw = source.get(_RUNTIME_REPLAY_ENV)
            self._enabled = (
                RUNTIME_REPLAY_VALIDATION_ENABLED if raw is None else raw.strip().lower() in {"1", "true", "yes", "on"}
            )
        else:
            self._enabled = enabled
        self._running = False

    @property
    def state(self) -> ReplayValidationState:
        if not self._enabled:
            return ReplayValidationState.DISABLED
        return ReplayValidationState.RUNNING if self._running else ReplayValidationState.READY

    def begin(self) -> bool:
        if not self._enabled or self._running:
            return False
        self._running = True
        return True

    def finish(self) -> None:
        self._running = False
