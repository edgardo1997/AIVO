from enum import Enum
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Any, Dict, List, Optional


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, cooldown_seconds: float = 30.0):
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds
        self._failures: Dict[str, int] = {}
        self._state: Dict[str, CircuitState] = {}
        self._last_failure_time: Dict[str, datetime] = {}
        self._last_success_time: Dict[str, datetime] = {}
        self._half_open_probe_active: Dict[str, bool] = {}
        self._lock = RLock()

    def record_success(self, provider_id: str) -> None:
        with self._lock:
            self._failures[provider_id] = 0
            self._state[provider_id] = CircuitState.CLOSED
            self._half_open_probe_active.pop(provider_id, None)
            self._last_success_time[provider_id] = datetime.now(timezone.utc)

    def record_failure(self, provider_id: str) -> None:
        with self._lock:
            count = self._failures.get(provider_id, 0) + 1
            self._failures[provider_id] = count
            self._last_failure_time[provider_id] = datetime.now(timezone.utc)
            if self._state.get(provider_id) == CircuitState.HALF_OPEN or count >= self._failure_threshold:
                self._state[provider_id] = CircuitState.OPEN
                self._half_open_probe_active.pop(provider_id, None)

    def allow_request(self, provider_id: str) -> bool:
        with self._lock:
            state = self._state.get(provider_id, CircuitState.CLOSED)
            if state == CircuitState.CLOSED:
                return True
            if state == CircuitState.OPEN:
                last_fail = self._last_failure_time.get(provider_id)
                if last_fail and (datetime.now(timezone.utc) - last_fail).total_seconds() >= self._cooldown_seconds:
                    self._state[provider_id] = CircuitState.HALF_OPEN
                    self._half_open_probe_active[provider_id] = True
                    return True
                return False
            # Only one recovery probe may run while half-open. Without this guard,
            # a burst after cooldown can immediately overload the dependency again.
            if self._half_open_probe_active.get(provider_id, False):
                return False
            self._half_open_probe_active[provider_id] = True
            return True

    def get_state(self, provider_id: str) -> Dict[str, Any]:
        with self._lock:
            state = self._state.get(provider_id, CircuitState.CLOSED)
            failures = self._failures.get(provider_id, 0)
            last_fail = self._last_failure_time.get(provider_id)
            last_success = self._last_success_time.get(provider_id)
            remaining_cooldown = 0.0
            if state == CircuitState.OPEN and last_fail:
                elapsed = (datetime.now(timezone.utc) - last_fail).total_seconds()
                remaining_cooldown = max(0.0, self._cooldown_seconds - elapsed)
            return {
                "provider_id": provider_id,
                "state": state.value,
                "consecutive_failures": failures,
                "failure_threshold": self._failure_threshold,
                "cooldown_seconds": self._cooldown_seconds,
                "remaining_cooldown": round(remaining_cooldown, 1),
                "last_failure": last_fail.isoformat() if last_fail else None,
                "last_success": last_success.isoformat() if last_success else None,
                "probe_in_flight": self._half_open_probe_active.get(provider_id, False),
            }

    def get_all_states(self) -> List[Dict[str, Any]]:
        provider_ids = set()
        with self._lock:
            provider_ids.update(self._state.keys())
            provider_ids.update(self._failures.keys())
        return [self.get_state(pid) for pid in sorted(provider_ids)]

    def reset(self, provider_id: Optional[str] = None) -> int:
        with self._lock:
            if provider_id:
                self._failures.pop(provider_id, None)
                self._state.pop(provider_id, None)
                self._last_failure_time.pop(provider_id, None)
                self._last_success_time.pop(provider_id, None)
                self._half_open_probe_active.pop(provider_id, None)
                return 1
            count = len(self._failures)
            self._failures.clear()
            self._state.clear()
            self._last_failure_time.clear()
            self._last_success_time.clear()
            self._half_open_probe_active.clear()
            return count
