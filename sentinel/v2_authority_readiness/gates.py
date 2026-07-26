"""Independent gates over sanitized aggregate evidence."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ReadinessEvidenceV1:
    contracts_available: bool
    versions_compatible: bool
    critical_contract_gaps: int
    shadow_match_rate: float
    critical_divergences: int
    conversion_errors: int
    identity_available: bool
    authorization_consistent: bool
    replay_detected: bool
    resolver_evidence_valid: bool
    completed_long_windows: int
    error_rate: float
    maximum_latency_ms: float
    lost_events: int
    direct_tool_execution: bool
    gateway_bypass: bool
    hidden_authority: bool


@dataclass(frozen=True)
class GateResult:
    gate_id: str
    passed: bool
    codes: tuple[str, ...]
    blocking: bool


def evaluate_contract_gate(evidence: ReadinessEvidenceV1) -> GateResult:
    codes = []
    if not evidence.contracts_available:
        codes.append("CONTRACTS_MISSING")
    if not evidence.versions_compatible:
        codes.append("VERSION_INCOMPATIBLE")
    if evidence.critical_contract_gaps:
        codes.append("CRITICAL_CONTRACT_GAP")
    return GateResult("CONTRACT", not codes, tuple(codes), bool(codes))


def evaluate_shadow_gate(evidence: ReadinessEvidenceV1) -> GateResult:
    codes = []
    if not 0 <= evidence.shadow_match_rate <= 1:
        codes.append("INVALID_MATCH_RATE")
    elif evidence.shadow_match_rate < 0.99:
        codes.append("MATCH_RATE_BELOW_THRESHOLD")
    if evidence.critical_divergences:
        codes.append("CRITICAL_DIVERGENCE")
    if evidence.conversion_errors:
        codes.append("CONVERSION_ERRORS")
    return GateResult(
        "SHADOW",
        not codes,
        tuple(codes),
        evidence.critical_divergences > 0,
    )


def evaluate_security_gate(evidence: ReadinessEvidenceV1) -> GateResult:
    codes = []
    if not evidence.identity_available:
        codes.append("IDENTITY_MISSING")
    if not evidence.authorization_consistent:
        codes.append("AUTHORIZATION_INCONSISTENT")
    if evidence.replay_detected:
        codes.append("REPLAY_DETECTED")
    if not evidence.resolver_evidence_valid:
        codes.append("RESOLVER_EVIDENCE_INVALID")
    return GateResult("SECURITY", not codes, tuple(codes), bool(codes))


def evaluate_stability_gate(evidence: ReadinessEvidenceV1) -> GateResult:
    codes = []
    if evidence.completed_long_windows < 3:
        codes.append("INSUFFICIENT_LONG_WINDOWS")
    if not 0 <= evidence.error_rate <= 1 or evidence.error_rate > 0.01:
        codes.append("ERROR_RATE_ABOVE_THRESHOLD")
    if evidence.maximum_latency_ms > 1000:
        codes.append("LATENCY_ABOVE_THRESHOLD")
    if evidence.lost_events:
        codes.append("EVENT_LOSS")
    return GateResult("STABILITY", not codes, tuple(codes), False)


def evaluate_boundary_gate(evidence: ReadinessEvidenceV1) -> GateResult:
    codes = []
    if evidence.direct_tool_execution:
        codes.append("DIRECT_TOOL_EXECUTION")
    if evidence.gateway_bypass:
        codes.append("GATEWAY_BYPASS")
    if evidence.hidden_authority:
        codes.append("HIDDEN_AUTHORITY")
    return GateResult("RUNTIME_BOUNDARY", not codes, tuple(codes), bool(codes))


def evaluate_all_gates(
    evidence: ReadinessEvidenceV1,
) -> tuple[GateResult, ...]:
    return (
        evaluate_contract_gate(evidence),
        evaluate_shadow_gate(evidence),
        evaluate_security_gate(evidence),
        evaluate_stability_gate(evidence),
        evaluate_boundary_gate(evidence),
    )
