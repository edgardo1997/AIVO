"""Human-readable V2 authority readiness evidence report."""

from dataclasses import dataclass

from .metrics import AuthorityReadinessMetricsSnapshot
from .validator import AuthorityReadinessResultV1


@dataclass(frozen=True)
class AuthorityReadinessReport:
    result: AuthorityReadinessResultV1
    metrics: AuthorityReadinessMetricsSnapshot

    def human_readable(self) -> str:
        passed = [gate.gate_id for gate in self.result.gates if gate.passed]
        failed = [gate.gate_id for gate in self.result.gates if not gate.passed]
        return (
            "SENTINEL V2 AUTHORITY READINESS REPORT\n\n"
            f"Estado general: {self.result.state.value}\n"
            f"Gates aprobados: {', '.join(passed) if passed else 'Ninguno'}\n"
            f"Gates fallidos: {', '.join(failed) if failed else 'Ninguno'}\n"
            f"Riesgos restantes: "
            f"{', '.join(self.result.risks) if self.result.risks else 'Ninguno'}\n"
            f"Validaciones: {self.metrics.validation_runs}\n"
            f"Recomendaciones: {', '.join(self.result.recommendations)}"
        )
