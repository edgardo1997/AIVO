"""Human-readable persistent safety report."""

from dataclasses import dataclass

from .metrics import AuthoritySafetyMetricsSnapshot
from .recovery import RecoveryStatus


@dataclass(frozen=True)
class AuthoritySafetyReport:
    recovery: RecoveryStatus
    metrics: AuthoritySafetyMetricsSnapshot
    risks: tuple[str, ...]
    recommendation: str

    def human_readable(self) -> str:
        return (
            "SENTINEL PERSISTENT AUTHORITY SAFETY REPORT\n\n"
            f"Recuperación: {self.recovery.value}\n"
            f"Operaciones iniciadas: {self.metrics.operations_started}\n"
            f"Committed: {self.metrics.operations_committed}\n"
            f"Rollback: {self.metrics.operations_rolled_back}\n"
            f"Replay rechazado: {self.metrics.replay_rejections}\n"
            f"Riesgos: {', '.join(self.risks) if self.risks else 'Ninguno'}\n"
            f"Recomendación: {self.recommendation}"
        )
