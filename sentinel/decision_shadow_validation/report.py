"""Human-readable aggregate decision shadow report."""

from dataclasses import dataclass

from .metrics import DecisionShadowMetricsSnapshot


@dataclass(frozen=True)
class DecisionShadowReport:
    metrics: DecisionShadowMetricsSnapshot
    critical_divergences: int
    risks: tuple[str, ...]
    recommendation: str

    def human_readable(self) -> str:
        rate = (
            self.metrics.matches / self.metrics.decisions_evaluated * 100 if self.metrics.decisions_evaluated else 0.0
        )
        return (
            "SENTINEL V2 DECISION SHADOW VALIDATION REPORT\n\n"
            f"Total evaluado: {self.metrics.decisions_evaluated}\n"
            f"Porcentaje coincidencia: {rate:.2f}%\n"
            f"Divergencias críticas: {self.critical_divergences}\n"
            f"Riesgos: {', '.join(self.risks) if self.risks else 'Ninguno'}\n"
            f"Recomendación: {self.recommendation}"
        )
