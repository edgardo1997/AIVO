"""Aggregate safety-layer counters."""

from dataclasses import dataclass
from threading import RLock


@dataclass(frozen=True)
class AuthoritySafetyMetricsSnapshot:
    operations_started: int
    operations_committed: int
    operations_rolled_back: int
    replay_rejections: int
    recovery_required: int
    recovery_blocked: int


class AuthoritySafetyMetrics:
    def __init__(self) -> None:
        self._lock = RLock()
        self._values = {
            "operations_started": 0,
            "operations_committed": 0,
            "operations_rolled_back": 0,
            "replay_rejections": 0,
            "recovery_required": 0,
            "recovery_blocked": 0,
        }

    def increment(self, metric: str) -> None:
        if metric not in self._values:
            raise ValueError("unknown aggregate metric")
        with self._lock:
            self._values[metric] += 1

    def snapshot(self) -> AuthoritySafetyMetricsSnapshot:
        with self._lock:
            return AuthoritySafetyMetricsSnapshot(**self._values)
