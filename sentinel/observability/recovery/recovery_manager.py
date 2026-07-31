"""Recovery Manager — graceful failure handling and system state management."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import logging
import time

from sentinel.observability.recovery.backup_manager import BackupManager

logger = logging.getLogger(__name__)


class SystemState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    RECOVERING = "recovering"
    FAILED = "failed"


@dataclass
class RecoveryPoint:
    id: str
    timestamp: str
    description: str = ""
    state_snapshot: Dict[str, Any] = field(default_factory=dict)
    backup_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "description": self.description,
            "backup_path": self.backup_path,
        }


RecoveryAction = Callable[[], bool]


class RecoveryManager:
    """Manages system state transitions, recovery points, and graceful degradation."""

    def __init__(self, backup_manager: Optional[BackupManager] = None):
        self._state: SystemState = SystemState.HEALTHY
        self._backup_manager = backup_manager
        self._recovery_points: List[RecoveryPoint] = []
        self._recovery_actions: Dict[str, RecoveryAction] = {}
        self._failure_counts: Dict[str, int] = {}
        self._state_history: List[Dict[str, Any]] = []
        self._start_time = time.monotonic()

    @property
    def state(self) -> SystemState:
        return self._state

    @state.setter
    def state(self, new_state: SystemState) -> None:
        old = self._state
        self._state = new_state
        self._state_history.append({
            "from": old.value,
            "to": new_state.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        logger.info("System state: %s → %s", old.value, new_state.value)

    def register_recovery_action(self, name: str, action: RecoveryAction) -> None:
        self._recovery_actions[name] = action

    def create_recovery_point(self, description: str = "", state_snapshot: Optional[Dict[str, Any]] = None) -> RecoveryPoint:
        import uuid
        rp = RecoveryPoint(
            id=uuid.uuid4().hex[:8],
            timestamp=datetime.now(timezone.utc).isoformat(),
            description=description,
            state_snapshot=state_snapshot or {},
            backup_path=self._backup_manager.latest_backup().path if self._backup_manager and self._backup_manager.latest_backup() else None,
        )
        self._recovery_points.append(rp)
        logger.info("Recovery point created: %s — %s", rp.id, description)
        return rp

    def record_failure(self, component: str) -> None:
        self._failure_counts[component] = self._failure_counts.get(component, 0) + 1

    def component_failure_rate(self, component: str) -> float:
        return self._failure_counts.get(component, 0) / max(time.monotonic() - self._start_time, 1) * 60

    def attempt_recovery(self, component: str) -> bool:
        self.state = SystemState.RECOVERING
        action = self._recovery_actions.get(component)
        if action is None:
            logger.warning("No recovery action registered for '%s'", component)
            self.state = SystemState.DEGRADED
            return False
        try:
            success = action()
            if success:
                self._failure_counts[component] = 0
                self.state = SystemState.HEALTHY
                logger.info("Recovery succeeded for '%s'", component)
            else:
                self.state = SystemState.DEGRADED
                logger.warning("Recovery failed for '%s'", component)
            return success
        except Exception as e:
            self.state = SystemState.FAILED
            logger.error("Recovery crashed for '%s': %s", component, e)
            return False

    def health_check(self) -> SystemState:
        if self._failure_counts and any(count > 3 for count in self._failure_counts.values()):
            self.state = SystemState.DEGRADED
        return self._state

    def summary(self) -> Dict[str, Any]:
        return {
            "state": self._state.value,
            "uptime_seconds": time.monotonic() - self._start_time,
            "recovery_points": len(self._recovery_points),
            "failure_counts": dict(self._failure_counts),
            "state_transitions": self._state_history[-10:],
            "registered_actions": list(self._recovery_actions.keys()),
        }
