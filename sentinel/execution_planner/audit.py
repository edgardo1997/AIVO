"""Planner audit and operational telemetry events."""

from sentinel.contracts import (
    AuditEventV1,
    EvidenceIntegrityStatusV1,
    ExecutionPlanResultV1,
    HealthStateV1,
)
from sentinel.operational_telemetry_hub import OperationalEventV1


def planner_events(
    result: ExecutionPlanResultV1,
    *,
    valid_origin: bool,
) -> tuple[AuditEventV1, OperationalEventV1]:
    audit = AuditEventV1(
        event_id=f"audit:{result.plan_id}",
        event_type="V2_EXECUTION_PLAN_EVALUATED",
        timestamp=result.timestamp,
        correlation_id=result.correlation_id,
        evidence_hash=result.evidence_hash,
        issuer_id=result.issuer_id,
        result=result.status.value,
    )
    operational = OperationalEventV1(
        event_id=f"telemetry:{result.plan_id}",
        correlation_id=result.correlation_id,
        evidence_hash=result.evidence_hash,
        issuer_id=result.issuer_id,
        timestamp=result.timestamp,
        event_type="V2_EXECUTION_PLAN_EVALUATED",
        health_state=HealthStateV1.OBSERVING,
        decision_state=result.status.value,
        integrity_status=(EvidenceIntegrityStatusV1.VERIFIED if valid_origin else EvidenceIntegrityStatusV1.INVALID),
    )
    return audit, operational
