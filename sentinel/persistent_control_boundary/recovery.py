"""Read-only recovery classification for persisted control state."""

from enum import Enum

from .schema import TERMINAL_STATES, PersistentControlState
from .storage import PersistentControlStorage


class PersistentRecoveryStatus(str, Enum):
    RECOVERY_OK = "RECOVERY_OK"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    RECOVERY_BLOCKED = "RECOVERY_BLOCKED"


class PersistentRecoveryInspector:
    def __init__(self, storage: PersistentControlStorage) -> None:
        self.storage = storage

    def inspect(self) -> PersistentRecoveryStatus:
        try:
            if not self.storage.integrity_check():
                return PersistentRecoveryStatus.RECOVERY_BLOCKED
            rows = self.storage.connection.execute("SELECT state FROM control_records").fetchall()
            states = tuple(PersistentControlState(row["state"]) for row in rows)
        except Exception:
            return PersistentRecoveryStatus.RECOVERY_BLOCKED
        if any(state not in TERMINAL_STATES for state in states):
            return PersistentRecoveryStatus.RECOVERY_REQUIRED
        return PersistentRecoveryStatus.RECOVERY_OK
