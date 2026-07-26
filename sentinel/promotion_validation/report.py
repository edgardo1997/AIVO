"""Structured and human-readable promotion validation report."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class PromotionValidationState(str, Enum):
    BLOCKED = "BLOCKED"
    READY_FOR_CANARY = "READY_FOR_CANARY"
    CANARY_APPROVED = "CANARY_APPROVED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class PromotionReport:
    validation_id: str
    timestamp: datetime
    state: PromotionValidationState
    approved_gates: tuple[str, ...]
    blocked_gates: tuple[str, ...]
    risks: tuple[str, ...]
    recommendations: tuple[str, ...]
    contract_versions: dict[str, str]

    def human_readable(self) -> str:
        approved = "\n".join(f"- {gate}" for gate in self.approved_gates) or "- Ninguno"
        blocked = "\n".join(f"- {gate}" for gate in self.blocked_gates) or "- Ninguno"
        risks = "\n".join(f"- {risk}" for risk in self.risks) or "- Ninguno"
        recommendations = "\n".join(f"- {item}" for item in self.recommendations)
        return (
            "SENTINEL PROMOTION VALIDATION REPORT\n\n"
            f"Estado final:\n{self.state.value}\n\n"
            f"Gates aprobados:\n{approved}\n\n"
            f"Gates bloqueados:\n{blocked}\n\n"
            f"Riesgos:\n{risks}\n\n"
            f"Recomendaciones:\n{recommendations}"
        )
