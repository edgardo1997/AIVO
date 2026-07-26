"""Human-readable activation gateway report."""

from dataclasses import dataclass

from .metrics import ActivationGatewayMetricsSnapshot


@dataclass(frozen=True)
class ActivationGatewayReport:
    metrics: ActivationGatewayMetricsSnapshot
    risks: tuple[str, ...]
    recommendation: str

    def human_readable(self) -> str:
        return (
            "SENTINEL V2 ACTIVATION GATEWAY REPORT\n\n"
            f"Evaluaciones: {self.metrics.total_evaluations}\n"
            f"Legacy seleccionado: {self.metrics.legacy_selected}\n"
            f"Candidatos V2: {self.metrics.v2_candidate_selected}\n"
            f"Bloqueos: {self.metrics.blocked}\n"
            f"Fallbacks: {self.metrics.fallbacks}\n"
            f"Errores: {self.metrics.errors}\n"
            f"Riesgos: {', '.join(self.risks) if self.risks else 'Ninguno'}\n"
            f"Recomendación: {self.recommendation}"
        )
