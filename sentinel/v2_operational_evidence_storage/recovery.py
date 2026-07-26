"""Recovery classification without mutating evidence."""

from enum import Enum

from .storage import OperationalEvidenceStorage


class RecoveryStatus(str, Enum):
    RECOVERY_OK = "RECOVERY_OK"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    RECOVERY_BLOCKED = "RECOVERY_BLOCKED"


class RecoveryManager:
    def inspect(self, storage: OperationalEvidenceStorage) -> RecoveryStatus:
        try:
            if not storage.integrity_ok():
                return RecoveryStatus.RECOVERY_BLOCKED
            if storage.unclean_start:
                return RecoveryStatus.RECOVERY_REQUIRED
        except Exception:
            return RecoveryStatus.RECOVERY_BLOCKED
        return RecoveryStatus.RECOVERY_OK
