"""Aggregate-only routing metrics."""

from dataclasses import dataclass
from threading import RLock


@dataclass(frozen=True)
class ActivationMetricsSnapshot:
    total_requests: int
    legacy_requests: int
    v2_canary_requests: int
    rollbacks: int
    failures: int
    blocked_requests: int


class ActivationMetrics:
    def __init__(self) -> None:
        self._lock = RLock()
        self._values = {
            "total_requests": 0,
            "legacy_requests": 0,
            "v2_canary_requests": 0,
            "rollbacks": 0,
            "failures": 0,
            "blocked_requests": 0,
        }

    def record_route(self, *, v2: bool, blocked: bool = False) -> None:
        with self._lock:
            self._values["total_requests"] += 1
            self._values["v2_canary_requests"] += int(v2)
            self._values["legacy_requests"] += int(not v2)
            self._values["blocked_requests"] += int(blocked)

    def record_rollback(self) -> None:
        with self._lock:
            self._values["rollbacks"] += 1

    def record_failure(self) -> None:
        with self._lock:
            self._values["failures"] += 1

    def record_pre_execution_fallback(
        self,
        *,
        route_was_v2: bool,
        route_was_counted: bool,
    ) -> None:
        with self._lock:
            if not route_was_counted:
                self._values["total_requests"] += 1
            elif route_was_v2:
                self._values["v2_canary_requests"] -= 1
            if not route_was_counted or route_was_v2:
                self._values["legacy_requests"] += 1
            self._values["rollbacks"] += 1
            self._values["blocked_requests"] += 1

    def snapshot(self) -> ActivationMetricsSnapshot:
        with self._lock:
            return ActivationMetricsSnapshot(**self._values)
