"""Gateway audit and operational event creation."""

from sentinel.contracts import (
    AuditEventV1,
    EvidenceIntegrityStatusV1,
    HealthStateV1,
    ToolGatewayDecisionResultV1,
)
from sentinel.operational_telemetry_hub import OperationalEventV1


def gateway_events(
    decision: ToolGatewayDecisionResultV1,
    *,
    integrity_status: EvidenceIntegrityStatusV1,
) -> tuple[AuditEventV1, OperationalEventV1]:
    audit = AuditEventV1(
        event_id=f"audit:{decision.decision_id}",
        event_type="V2_TOOL_GATEWAY_EVALUATED",
        timestamp=decision.timestamp,
        correlation_id=decision.correlation_id,
        evidence_hash=decision.evidence_hash,
        issuer_id=decision.issuer_id,
        result=decision.decision.value,
    )
    operational = OperationalEventV1(
        event_id=f"telemetry:{decision.decision_id}",
        correlation_id=decision.correlation_id,
        evidence_hash=decision.evidence_hash,
        issuer_id=decision.issuer_id,
        timestamp=decision.timestamp,
        event_type="V2_TOOL_GATEWAY_EVALUATED",
        health_state=HealthStateV1.OBSERVING,
        decision_state=decision.decision.value,
        integrity_status=integrity_status,
    )
    return audit, operational
