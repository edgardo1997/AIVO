"""Structured and human-readable stability validation report."""

from dataclasses import dataclass
from datetime import datetime

from .collector import StabilityMetrics
from .health import StabilityStatus


@dataclass(frozen=True)
class StabilityReport:
    validation_id: str
    started_at: datetime
    ended_at: datetime
    observed_duration_seconds: float
    evaluated_components: tuple[str, ...]
    status: StabilityStatus
    metrics: StabilityMetrics
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]

    def human_readable(self) -> str:
        comparison_total = self.metrics.comparison_matches + self.metrics.comparison_divergences
        comparison_rate = 100.0 * self.metrics.comparison_matches / comparison_total if comparison_total else 0.0
        warning_text = "\n".join(f"- {item}" for item in self.warnings) if self.warnings else "Ninguna"
        return (
            "SENTINEL STABILITY VALIDATION REPORT\n\n"
            f"Estado:\n{self.status.value}\n\n"
            f"Duración:\n{self.observed_duration_seconds / 3600:.2f} horas\n\n"
            f"Eventos observados:\n{self.metrics.total_events}\n\n"
            f"Comparación V2:\n{comparison_rate:.2f}%\n\n"
            f"Memoria:\n{self.metrics.memory_delta:+.2f} MB\n\n"
            f"Errores:\n{self.metrics.error_rate * 100:.4f}%\n\n"
            f"Advertencias:\n{warning_text}\n\n"
            "Recomendación:\nContinuar observación antes de cutover."
        )
