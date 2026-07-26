"""Human-readable report for aggregate canary environment evidence."""

from dataclasses import dataclass

from .environment import CanaryEnvironmentV1
from .health import CanaryHealthStatus
from .metrics import CanaryMetricsSnapshot


@dataclass(frozen=True)
class CanaryEnvironmentReport:
    state: str
    active_duration_seconds: float
    health: CanaryHealthStatus
    metrics: CanaryMetricsSnapshot
    risks: tuple[str, ...]
    recommendations: tuple[str, ...]

    @classmethod
    def build(
        cls,
        environment: CanaryEnvironmentV1,
        *,
        active_duration_seconds: float,
        health: CanaryHealthStatus,
        metrics: CanaryMetricsSnapshot,
        risks: tuple[str, ...] = (),
    ) -> "CanaryEnvironmentReport":
        recommendations = (
            ("continue_isolated_observation",)
            if health is CanaryHealthStatus.HEALTHY
            else ("do_not_promote_authority", "review_canary_health")
        )
        return cls(
            state=environment.state.value,
            active_duration_seconds=max(0.0, active_duration_seconds),
            health=health,
            metrics=metrics,
            risks=risks,
            recommendations=recommendations,
        )

    def human_readable(self) -> str:
        return (
            "SENTINEL CONTROLLED CANARY ENVIRONMENT REPORT\n\n"
            f"Estado actual: {self.state}\n"
            f"Duración activa: {self.active_duration_seconds:.2f}s\n"
            f"Salud: {self.health.value}\n"
            f"Eventos procesados: {self.metrics.processed_events}\n"
            f"Errores: {self.metrics.errors}\n"
            f"Coincidencias: {self.metrics.matches}\n"
            f"Divergencias: {self.metrics.divergences}\n"
            f"Riesgos: {', '.join(self.risks) if self.risks else 'Ninguno'}\n"
            f"Recomendaciones: {', '.join(self.recommendations)}"
        )
