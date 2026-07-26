"""Independent readiness gates over consolidated aggregate signals."""

from dataclasses import dataclass

from .signals import ConsolidatedSignalsV1


@dataclass(frozen=True)
class GateResult:
    gate_id: str
    passed: bool
    codes: tuple[str, ...]
    blocking: bool


def safety_gate(signals: ConsolidatedSignalsV1) -> GateResult:
    codes = []
    if not signals.safety_healthy:
        codes.append("SAFETY_NOT_HEALTHY")
    if signals.recovery_status in {"BLOCKED_RECOVERY", "RECOVERY_BLOCKED"}:
        codes.append("RECOVERY_BLOCKED")
    elif signals.recovery_status == "RECOVERY_REQUIRED":
        codes.append("RECOVERY_PENDING")
    if signals.state_corrupted:
        codes.append("STATE_CORRUPTION")
    return GateResult("SAFETY", not codes, tuple(codes), bool(codes))


def evidence_gate(signals: ConsolidatedSignalsV1) -> GateResult:
    codes = []
    if not signals.evidence_available:
        codes.append("EVIDENCE_UNAVAILABLE")
    if not signals.evidence_integrity_valid:
        codes.append("EVIDENCE_INTEGRITY_INVALID")
    if signals.critical_data_loss:
        codes.append("CRITICAL_DATA_LOSS")
    return GateResult(
        "EVIDENCE",
        not codes,
        tuple(codes),
        "EVIDENCE_INTEGRITY_INVALID" in codes or "CRITICAL_DATA_LOSS" in codes,
    )


def runtime_gate(signals: ConsolidatedSignalsV1) -> GateResult:
    codes = []
    if signals.runtime_equivalence_rate < 0.99:
        codes.append("EQUIVALENCE_INSUFFICIENT")
    if signals.critical_divergences:
        codes.append("CRITICAL_DIVERGENCE")
    if signals.operational_health not in {"HEALTHY", "OBSERVING"}:
        codes.append("HEALTH_NOT_ACCEPTABLE")
    return GateResult(
        "RUNTIME",
        not codes,
        tuple(codes),
        signals.critical_divergences > 0 or signals.operational_health in {"DEGRADED", "CRITICAL"},
    )


def trust_gate(signals: ConsolidatedSignalsV1) -> GateResult:
    codes = []
    if signals.trust_score is None:
        codes.append("TRUST_SCORE_UNAVAILABLE")
    elif signals.trust_score < 65:
        codes.append("TRUST_SCORE_INSUFFICIENT")
    if signals.trust_confidence in {"UNKNOWN", "LOW_CONFIDENCE"}:
        codes.append("CONFIDENCE_INSUFFICIENT")
    if signals.trust_recommendation in {
        "NO_RECOMMENDATION",
        "BLOCK_MIGRATION",
    }:
        codes.append("TRUST_RECOMMENDATION_INCOMPATIBLE")
    return GateResult(
        "TRUST",
        not codes,
        tuple(codes),
        signals.trust_recommendation == "BLOCK_MIGRATION",
    )


def activation_gate(signals: ConsolidatedSignalsV1) -> GateResult:
    codes = []
    if signals.controlled_activation_enabled:
        codes.append("CONTROLLED_ACTIVATION_MUST_REMAIN_DISABLED")
    if signals.v2_canary_enabled:
        codes.append("V2_CANARY_MUST_REMAIN_DISABLED")
    return GateResult("ACTIVATION", not codes, tuple(codes), bool(codes))


def evaluate_gates(
    signals: ConsolidatedSignalsV1,
) -> tuple[GateResult, ...]:
    return (
        safety_gate(signals),
        evidence_gate(signals),
        runtime_gate(signals),
        trust_gate(signals),
        activation_gate(signals),
    )
