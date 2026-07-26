"""Human-readable controlled migration report."""

from dataclasses import dataclass

from .control import AuthorityMigrationState
from .metrics import AuthorityMigrationMetricsSnapshot


@dataclass(frozen=True)
class AuthorityMigrationReport:
    state: AuthorityMigrationState
    metrics: AuthorityMigrationMetricsSnapshot
    risks: tuple[str, ...]
    recommendation: str

    def human_readable(self) -> str:
        return (
            "SENTINEL CONTROLLED V2 AUTHORITY MIGRATION REPORT\n\n"
            f"Estado: {self.state.value}\n"
            f"Decisiones: {self.metrics.routing_decisions}\n"
            f"Legacy: {self.metrics.legacy_selections}\n"
            f"V2 limitado: {self.metrics.v2_selections}\n"
            f"Fallbacks: {self.metrics.fallbacks}\n"
            f"Rollbacks: {self.metrics.rollbacks}\n"
            f"Riesgos: {', '.join(self.risks) if self.risks else 'Ninguno'}\n"
            f"Recomendación: {self.recommendation}"
        )
