"""Sandbox audit and operational events."""

from sentinel.contracts import (
    AuditEventV1,
    EvidenceIntegrityStatusV1,
    HealthStateV1,
    SandboxSimulationResultV1,
)
from sentinel.operational_telemetry_hub import OperationalEventV1


def sandbox_events(
    result: SandboxSimulationResultV1,
    *,
    valid_evidence: bool,
) -> tuple[AuditEventV1, OperationalEventV1]:
    audit = AuditEventV1(
        event_id=f"audit:{result.simulation_id}",
        event_type="V2_SANDBOX_SIMULATED",
        timestamp=result.timestamp,
        correlation_id=result.correlation_id,
        evidence_hash=result.evidence_hash,
        issuer_id=result.issuer_id,
        result=result.status.value,
    )
    operational = OperationalEventV1(
        event_id=f"telemetry:{result.simulation_id}",
        correlation_id=result.correlation_id,
        evidence_hash=result.evidence_hash,
        issuer_id=result.issuer_id,
        timestamp=result.timestamp,
        event_type="V2_SANDBOX_SIMULATED",
        health_state=HealthStateV1.OBSERVING,
        decision_state=result.status.value,
        integrity_status=(EvidenceIntegrityStatusV1.VERIFIED if valid_evidence else EvidenceIntegrityStatusV1.INVALID),
    )
    return audit, operational
