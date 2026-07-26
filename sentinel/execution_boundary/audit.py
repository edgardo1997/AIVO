"""Central audit and telemetry event construction."""

from sentinel.contracts import (
    AuditEventV1,
    EvidenceIntegrityStatusV1,
    ExecutionBoundaryDecisionResultV1,
    HealthStateV1,
)
from sentinel.operational_telemetry_hub import OperationalEventV1


def boundary_events(
    result: ExecutionBoundaryDecisionResultV1,
    *,
    valid_origin: bool,
) -> tuple[AuditEventV1, OperationalEventV1]:
    audit = AuditEventV1(
        event_id=f"audit:{result.decision_id}",
        event_type="V2_EXECUTION_BOUNDARY_EVALUATED",
        timestamp=result.timestamp,
        correlation_id=result.correlation_id,
        evidence_hash=result.evidence_hash,
        issuer_id=result.issuer_id,
        result=result.decision.value,
    )
    operational = OperationalEventV1(
        event_id=f"telemetry:{result.decision_id}",
        correlation_id=result.correlation_id,
        evidence_hash=result.evidence_hash,
        issuer_id=result.issuer_id,
        timestamp=result.timestamp,
        event_type="V2_EXECUTION_BOUNDARY_EVALUATED",
        health_state=HealthStateV1.OBSERVING,
        decision_state=result.decision.value,
        integrity_status=(EvidenceIntegrityStatusV1.VERIFIED if valid_origin else EvidenceIntegrityStatusV1.INVALID),
    )
    return audit, operational
