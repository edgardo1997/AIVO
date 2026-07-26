"""Human-readable controlled activation report."""

from dataclasses import dataclass

from .activation import ActivationState
from .health import ActivationHealthStatus
from .metrics import ActivationMetricsSnapshot


@dataclass(frozen=True)
class ActivationReport:
    state: ActivationState
    health: ActivationHealthStatus
    metrics: ActivationMetricsSnapshot
    risks: tuple[str, ...]
    recommendation: str

    def human_readable(self) -> str:
        return (
            "SENTINEL CONTROLLED RUNTIME ACTIVATION REPORT\n\n"
            f"Estado: {self.state.value}\n"
            f"Salud: {self.health.value}\n"
            f"Solicitudes: {self.metrics.total_requests}\n"
            f"Legacy: {self.metrics.legacy_requests}\n"
            f"V2 canary: {self.metrics.v2_canary_requests}\n"
            f"Rollbacks: {self.metrics.rollbacks}\n"
            f"Riesgos: {', '.join(self.risks) if self.risks else 'Ninguno'}\n"
            f"Recomendación: {self.recommendation}"
        )
