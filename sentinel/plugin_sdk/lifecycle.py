"""Plugin lifecycle state machine.

Every plugin must pass through the same stages: installed → validated →
permission review → active → executing → deactivated. Transitions are
explicit and validated so a plugin can never skip a security gate.
"""

from __future__ import annotations

from typing import Dict, Iterable

STATE_INSTALLED = "installed"
STATE_VALIDATED = "validated"
STATE_PERMISSION_REVIEW = "permission_review"
STATE_ACTIVE = "active"
STATE_EXECUTING = "executing"
STATE_DEACTIVATED = "deactivated"
STATE_ERROR = "error"

STATES = (
    STATE_INSTALLED,
    STATE_VALIDATED,
    STATE_PERMISSION_REVIEW,
    STATE_ACTIVE,
    STATE_EXECUTING,
    STATE_DEACTIVATED,
    STATE_ERROR,
)

_ALLOWED: Dict[str, set] = {
    STATE_INSTALLED: {STATE_VALIDATED, STATE_DEACTIVATED, STATE_ERROR},
    STATE_VALIDATED: {STATE_PERMISSION_REVIEW, STATE_DEACTIVATED, STATE_ERROR},
    STATE_PERMISSION_REVIEW: {STATE_ACTIVE, STATE_DEACTIVATED, STATE_ERROR},
    STATE_ACTIVE: {STATE_EXECUTING, STATE_DEACTIVATED, STATE_ERROR},
    STATE_EXECUTING: {STATE_ACTIVE, STATE_DEACTIVATED, STATE_ERROR},
    STATE_DEACTIVATED: {STATE_INSTALLED, STATE_ERROR},
    STATE_ERROR: {STATE_INSTALLED, STATE_DEACTIVATED},
}


class LifecycleError(RuntimeError):
    pass


class PluginLifecycle:
    def __init__(self, initial: str = STATE_INSTALLED) -> None:
        if initial not in STATES:
            raise ValueError(f"unknown lifecycle state: {initial}")
        self._state = initial

    @property
    def state(self) -> str:
        return self._state

    def can(self, target: str) -> bool:
        return target in _ALLOWED.get(self._state, set())

    def transition(self, target: str) -> str:
        if target not in STATES:
            raise LifecycleError(f"unknown lifecycle state: {target}")
        if target == self._state:
            return self._state
        if not self.can(target):
            raise LifecycleError(f"cannot transition plugin from '{self._state}' to '{target}'")
        self._state = target
        return self._state

    def to_dict(self) -> Dict[str, str]:
        return {"state": self._state, "transitions": sorted(_ALLOWED.get(self._state, set()))}


def normalize_state(value: str) -> str:
    return value if value in STATES else STATE_ERROR
