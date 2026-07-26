"""Human-readable aggregate long-term evaluation report."""

from dataclasses import dataclass

from .aggregation import DecisionAggregateSnapshot
from .health import DecisionLongTermHealthStatus
from .trend import TrendStatus
from .window import EvaluationWindowV1


@dataclass(frozen=True)
class DecisionLongTermReport:
    window: EvaluationWindowV1
    metrics: DecisionAggregateSnapshot
    trend: TrendStatus
    health: DecisionLongTermHealthStatus
    risks: tuple[str, ...]
    recommendation: str

    def human_readable(self) -> str:
        return (
            "SENTINEL DECISION SHADOW LONG TERM REPORT\n\n"
            f"Ventana evaluada: {self.window.evaluation_id}\n"
            f"Duración: {self.window.duration_seconds:.2f}s\n"
            f"Cantidad de decisiones: {self.metrics.total_decisions}\n"
            f"Estabilidad: {self.health.value}\n"
            f"Tendencia: {self.trend.value}\n"
            f"Riesgos: {', '.join(self.risks) if self.risks else 'Ninguno'}\n"
            f"Recomendación: {self.recommendation}"
        )
