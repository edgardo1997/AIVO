"""Human-readable operational evidence storage report."""

from dataclasses import dataclass

from .metrics import EvidenceStorageMetricsSnapshot
from .recovery import RecoveryStatus


@dataclass(frozen=True)
class EvidenceStorageReport:
    storage_state: str
    integrity_valid: bool
    recovery: RecoveryStatus
    metrics: EvidenceStorageMetricsSnapshot
    risks: tuple[str, ...]

    def human_readable(self) -> str:
        return (
            "SENTINEL V2 OPERATIONAL EVIDENCE STORAGE REPORT\n\n"
            f"Estado del almacenamiento: {self.storage_state}\n"
            f"Integridad: {'VALID' if self.integrity_valid else 'INVALID'}\n"
            f"Recuperación: {self.recovery.value}\n"
            f"Registros: {self.metrics.total_records}\n"
            f"Fallos de integridad: {self.metrics.integrity_failures}\n"
            f"Eliminados: {self.metrics.deleted_records}\n"
            f"Errores: {self.metrics.storage_errors}\n"
            f"Riesgos: {', '.join(self.risks) if self.risks else 'Ninguno'}"
        )
