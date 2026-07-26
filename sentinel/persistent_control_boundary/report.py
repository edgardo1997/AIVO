"""Human-readable summary for the isolated persistent boundary."""

from dataclasses import dataclass

from .metrics import PersistentControlMetricsSnapshot
from .recovery import PersistentRecoveryStatus


@dataclass(frozen=True)
class PersistentControlBoundaryReport:
    enabled: bool
    recovery_status: PersistentRecoveryStatus
    metrics: PersistentControlMetricsSnapshot
    risks: tuple[str, ...]
    authority: bool = False
    execution_requested: bool = False

    def render(self) -> str:
        return "\n".join(
            (
                "SENTINEL V2 PERSISTENT CONTROL BOUNDARY REPORT",
                f"Enabled: {self.enabled}",
                f"Recovery: {self.recovery_status.value}",
                f"Reservations: {self.metrics.reservations}",
                f"Rollbacks: {self.metrics.rollbacks}",
                f"Risks: {', '.join(self.risks) if self.risks else 'None'}",
                "Authority: false",
                "Execution requested: false",
            )
        )
