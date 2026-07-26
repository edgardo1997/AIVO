"""Sandbox execution audit and telemetry events."""

from sentinel.contracts import (
    AuditEventV1,
    EvidenceIntegrityStatusV1,
    HealthStateV1,
    SandboxExecutionResultV1,
)
from sentinel.operational_telemetry_hub import OperationalEventV1


def execution_events(
    result: SandboxExecutionResultV1,
    *,
    valid_origin: bool,
) -> tuple[AuditEventV1, OperationalEventV1]:
    audit = AuditEventV1(
        event_id=f"audit:{result.execution_id}",
        event_type="V2_SANDBOX_EXECUTION_SIMULATED",
        timestamp=result.timestamp,
        correlation_id=result.correlation_id,
        evidence_hash=result.evidence_hash,
        issuer_id=result.issuer_id,
        result=result.final_state.value,
    )
    operational = OperationalEventV1(
        event_id=f"telemetry:{result.execution_id}",
        correlation_id=result.correlation_id,
        evidence_hash=result.evidence_hash,
        issuer_id=result.issuer_id,
        timestamp=result.timestamp,
        event_type="V2_SANDBOX_EXECUTION_SIMULATED",
        health_state=HealthStateV1.OBSERVING,
        decision_state=result.final_state.value,
        integrity_status=(EvidenceIntegrityStatusV1.VERIFIED if valid_origin else EvidenceIntegrityStatusV1.INVALID),
    )
    return audit, operational
