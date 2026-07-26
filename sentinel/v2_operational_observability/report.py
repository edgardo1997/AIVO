"""Human-readable aggregate operational observability report."""

from dataclasses import dataclass

from .alerts import AlertRecommendation
from .health import OperationalHealthStatus
from .metrics import OperationalMetricsSnapshot


@dataclass(frozen=True)
class OperationalReport:
    current_health: OperationalHealthStatus
    incidents_detected: int
    metrics: OperationalMetricsSnapshot
    recommendations: tuple[AlertRecommendation, ...]
    risks: tuple[str, ...]

    def human_readable(self) -> str:
        recommendations = ", ".join(item.value for item in self.recommendations)
        return (
            "SENTINEL V2 OPERATIONAL OBSERVABILITY REPORT\n\n"
            f"Estado actual: {self.current_health.value}\n"
            f"Incidentes detectados: {self.incidents_detected}\n"
            f"Eventos: {self.metrics.total_events}\n"
            f"Error rate: {self.metrics.error_rate:.4f}\n"
            f"Divergence rate: {self.metrics.divergence_rate:.4f}\n"
            f"Rollbacks: {self.metrics.rollback_count}\n"
            f"Recomendaciones: {recommendations or 'NO_ACTION'}\n"
            f"Riesgos: {', '.join(self.risks) if self.risks else 'Ninguno'}"
        )
