"""Promotion evidence validation with no activation side effects."""

import re
import uuid
from datetime import datetime, timezone

from .control import promotion_validation_enabled
from .gates import (
    BoundaryGate,
    ContractGate,
    GateResult,
    PromotionEvidence,
    SecurityGate,
    ShadowGate,
    StabilityGate,
)
from .metrics import PromotionMetrics
from .promotion_plan import PromotionPlanV1
from .report import PromotionReport, PromotionValidationState


class PromotionValidationEngine:
    """Evaluate gates only; never promotes or activates a component."""

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        metrics: PromotionMetrics | None = None,
    ) -> None:
        self._enabled = promotion_validation_enabled() if enabled is None else enabled
        self.metrics = metrics or PromotionMetrics()
        self._gates = (
            ContractGate(),
            ShadowGate(),
            SecurityGate(),
            StabilityGate(),
            BoundaryGate(),
        )

    @property
    def enabled(self) -> bool:
        return self._enabled

    def validate(
        self,
        plan: PromotionPlanV1,
        evidence: PromotionEvidence,
    ) -> PromotionReport:
        timestamp = datetime.now(timezone.utc)
        if not self._enabled:
            return PromotionReport(
                validation_id="promotion_validation_disabled",
                timestamp=timestamp,
                state=PromotionValidationState.BLOCKED,
                approved_gates=(),
                blocked_gates=("promotion_validation_disabled",),
                risks=("validation_disabled",),
                recommendations=("No promover; habilitar validación explícita.",),
                contract_versions={},
            )

        results = tuple(gate.evaluate(plan, evidence) for gate in self._gates)
        approved = tuple(result.gate for result in results if result.passed)
        blocked = tuple(result.gate for result in results if not result.passed)
        risks = _risk_codes(plan, results)
        missing_approvals = set(plan.approval_requirements) - evidence.approvals
        if evidence.approval_rejected:
            state = PromotionValidationState.REJECTED
            recommendations = (
                "Mantener el componente en shadow.",
                "Registrar el rechazo sin modificar runtime.",
            )
        elif blocked:
            state = PromotionValidationState.BLOCKED
            recommendations = (
                "No promover a canary.",
                "Resolver todos los gates bloqueados y repetir validación.",
            )
        elif missing_approvals:
            state = PromotionValidationState.READY_FOR_CANARY
            recommendations = (
                "La evidencia permite considerar una promoción futura.",
                "Obtener aprobaciones restantes; no activar todavía.",
            )
        else:
            state = PromotionValidationState.CANARY_APPROVED
            recommendations = (
                "Aprobación documental completa.",
                "La activación requiere una fase separada y explícita.",
            )
        report = PromotionReport(
            validation_id=f"promotion_validation_{uuid.uuid4().hex}",
            timestamp=timestamp,
            state=state,
            approved_gates=approved,
            blocked_gates=blocked,
            risks=risks,
            recommendations=recommendations,
            contract_versions=_safe_versions(evidence.contract_versions),
        )
        self.metrics.record(
            report,
            divergences=evidence.divergences_total,
            errors=evidence.critical_errors,
        )
        return report


def _risk_codes(
    plan: PromotionPlanV1,
    results: tuple[GateResult, ...],
) -> tuple[str, ...]:
    values = [reason for result in results for reason in result.reasons]
    if plan.known_risks:
        values.append(f"declared_risk_count:{len(plan.known_risks)}")
    return tuple(dict.fromkeys(values))


def _safe_versions(values: dict[str, str]) -> dict[str, str]:
    safe = {}
    pattern = re.compile(r"^[A-Za-z0-9._+-]{1,32}$")
    for key, value in values.items():
        if key in {
            "IntentV2",
            "ExecutionPlanV2",
            "PolicyDecisionV2Strict",
            "AuthorizationGrantV1",
            "ApplicationDescriptorV1",
        }:
            safe[key] = value if pattern.fullmatch(value) else "REDACTED"
    return safe
