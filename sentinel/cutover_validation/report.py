"""Machine-readable and human-readable cutover readiness report."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from .classification import ClassifiedDivergence


class CutoverReadinessState(str, Enum):
    READY = "READY"
    WARNING = "WARNING"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class CutoverReadinessReport:
    validation_id: str
    timestamp: datetime
    evaluated_components: tuple[str, ...]
    overall_state: CutoverReadinessState
    metrics_summary: dict[str, int | float]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    recommendations: tuple[str, ...]
    divergences: tuple[ClassifiedDivergence, ...]
    checklist: dict[str, dict[str, bool]]

    def human_readable(self) -> str:
        policy = self.metrics_summary.get("policy_match_rate", 0.0)
        discovery = self.metrics_summary.get(
            "discovery_match_rate",
            0.0,
        )
        authorization = self.metrics_summary.get(
            "authorization_match_rate",
            0.0,
        )
        blocker_text = "\n".join(f"- {item}" for item in self.blockers) if self.blockers else "- Ninguno"
        recommendation_text = "\n".join(f"- {item}" for item in self.recommendations)
        return (
            "SENTINEL CUTOVER READINESS REPORT\n\n"
            f"Estado:\n{self.overall_state.value}\n\n"
            "Componentes:\n"
            f"- Policy V2: {policy:.2f}% coincidencia\n"
            f"- Discovery V2: {discovery:.2f}% coincidencia\n"
            f"- Authorization: {authorization:.2f}% coincidencia\n\n"
            f"Bloqueadores:\n{blocker_text}\n\n"
            f"Recomendación:\n{recommendation_text}"
        )
