"""Human-readable aggregate equivalence report."""

from dataclasses import dataclass

from .metrics import EquivalenceMetricsSnapshot


@dataclass(frozen=True)
class RuntimeEquivalenceReport:
    metrics: EquivalenceMetricsSnapshot
    risks: tuple[str, ...]
    recommendation: str

    def human_readable(self) -> str:
        rate = self.metrics.matches / self.metrics.comparisons * 100 if self.metrics.comparisons else 0.0
        return (
            "SENTINEL RUNTIME EQUIVALENCE VALIDATION REPORT\n\n"
            f"Comparaciones: {self.metrics.comparisons}\n"
            f"Coincidencias: {self.metrics.matches}\n"
            f"Divergencias: {self.metrics.divergences}\n"
            f"Errores: {self.metrics.errors}\n"
            f"Equivalencia: {rate:.2f}%\n"
            f"Riesgos: {', '.join(self.risks) if self.risks else 'Ninguno'}\n"
            f"Recomendación: {self.recommendation}"
        )
