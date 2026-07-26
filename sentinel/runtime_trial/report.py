"""Human-readable aggregate report for controlled V2 trials."""

from dataclasses import dataclass

from .health import RuntimeTrialHealthStatus
from .metrics import RuntimeTrialMetricsSnapshot


@dataclass(frozen=True)
class RuntimeTrialReport:
    health: RuntimeTrialHealthStatus
    metrics: RuntimeTrialMetricsSnapshot
    scenarios: tuple[str, ...]
    risks: tuple[str, ...]

    def human_readable(self) -> str:
        return (
            "SENTINEL CONTROLLED V2 RUNTIME TRIAL REPORT\n\n"
            f"Escenarios ejecutados: {self.metrics.scenarios_run}\n"
            f"Éxitos: {self.metrics.successes}\n"
            f"Fallos: {self.metrics.failures}\n"
            f"Divergencias: {self.metrics.divergences}\n"
            f"Salud: {self.health.value}\n"
            f"Riesgos: {', '.join(self.risks) if self.risks else 'Ninguno'}"
        )
