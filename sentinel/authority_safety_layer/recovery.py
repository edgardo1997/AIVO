"""Diagnostic recovery classification; never resumes execution."""

from enum import Enum

from .storage import AuthoritySafetyStorage


class RecoveryStatus(str, Enum):
    SAFE_RECOVERY = "SAFE_RECOVERY"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    BLOCKED_RECOVERY = "BLOCKED_RECOVERY"


class RecoveryManager:
    def inspect(self, storage: AuthoritySafetyStorage) -> RecoveryStatus:
        try:
            if not storage.integrity_ok():
                return RecoveryStatus.BLOCKED_RECOVERY
            if storage.pending():
                return RecoveryStatus.RECOVERY_REQUIRED
        except Exception:
            return RecoveryStatus.BLOCKED_RECOVERY
        return RecoveryStatus.SAFE_RECOVERY
