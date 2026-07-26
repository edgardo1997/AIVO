"""Plain-language final control-plane readiness report."""

from dataclasses import dataclass

from .decision import FinalReadinessDecision


@dataclass(frozen=True)
class FinalReadinessReport:
    decision: FinalReadinessDecision
    remaining_risks: tuple[str, ...]
    recommendation: str

    def human_readable(self) -> str:
        passed = ", ".join(self.decision.passed_gates) or "Ninguno"
        failed = ", ".join(self.decision.failed_gates) or "Ninguno"
        risks = ", ".join(self.remaining_risks) or "Ninguno"
        return (
            "SENTINEL FINAL CONTROL PLANE READINESS REPORT\n\n"
            f"Estado actual: {self.decision.status.value}\n"
            f"Confianza: {self.decision.confidence:.2f}%\n"
            f"Controles aprobados: {passed}\n"
            f"Controles pendientes: {failed}\n"
            f"Riesgos restantes: {risks}\n"
            f"Recomendación: {self.recommendation}"
        )
