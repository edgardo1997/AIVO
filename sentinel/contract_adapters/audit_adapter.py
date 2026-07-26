"""Adapter for sanitized audit events emitted by existing V2 modules."""

from datetime import datetime
import uuid

from sentinel.contracts import AuditEventV1

from .authority_adapter import (
    AdaptedContractV1,
    build_adapter_metadata,
    validate_non_authoritative_source,
)


def adapt_audit(
    source: object,
    *,
    correlation_id: str,
    event_type: str,
    result: str,
    issuer_id: str | None = None,
    event_id: str | None = None,
    timestamp: datetime | None = None,
) -> AdaptedContractV1[AuditEventV1]:
    """Create a central audit fact without retaining the source payload."""

    validate_non_authoritative_source(source)
    metadata = build_adapter_metadata(
        source,
        correlation_id=correlation_id,
        timestamp=timestamp,
    )
    event = AuditEventV1(
        event_id=event_id or f"audit:{uuid.uuid4().hex}",
        event_type=event_type,
        timestamp=metadata.timestamp,
        correlation_id=metadata.correlation_id,
        evidence_hash=metadata.evidence_hash,
        issuer_id=issuer_id or type(source).__module__,
        result=result,
    )
    return AdaptedContractV1(contract=event, metadata=metadata)
