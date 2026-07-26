"""Adapter for existing V2 readiness classifications."""

from datetime import datetime
from enum import Enum

from sentinel.contracts import ReadinessStateV1, ReadinessStateValueV1

from .authority_adapter import (
    AdaptedContractV1,
    build_adapter_metadata,
    validate_non_authoritative_source,
)

_READINESS_MAP = {
    "BLOCKED": ReadinessStateValueV1.BLOCKED,
    "NOT_READY": ReadinessStateValueV1.INSUFFICIENT_EVIDENCE,
    "INSUFFICIENT_EVIDENCE": ReadinessStateValueV1.INSUFFICIENT_EVIDENCE,
    "READY_FOR_REVIEW": ReadinessStateValueV1.READY_FOR_HUMAN_REVIEW,
    "READY_FOR_HUMAN_REVIEW": ReadinessStateValueV1.READY_FOR_HUMAN_REVIEW,
    "APPROVED_FOR_MIGRATION": ReadinessStateValueV1.HIGH_CONFIDENCE_REVIEW,
    "HIGH_CONFIDENCE_REVIEW": ReadinessStateValueV1.HIGH_CONFIDENCE_REVIEW,
    "NOT_APPROVED": ReadinessStateValueV1.NOT_APPROVED,
}


def adapt_readiness(
    source: object,
    *,
    correlation_id: str,
    state: str | Enum | None = None,
    timestamp: datetime | None = None,
) -> AdaptedContractV1[ReadinessStateV1]:
    """Normalize readiness without interpreting it as activation authority."""

    validate_non_authoritative_source(source)
    raw_state = state if state is not None else getattr(source, "status", source)
    normalized = raw_state.value if isinstance(raw_state, Enum) else str(raw_state)
    try:
        readiness_state = _READINESS_MAP[normalized.upper()]
    except KeyError as exc:
        raise ValueError(f"unsupported readiness state: {normalized}") from exc
    metadata = build_adapter_metadata(
        source,
        correlation_id=correlation_id,
        timestamp=timestamp,
    )
    return AdaptedContractV1(
        contract=ReadinessStateV1(state=readiness_state),
        metadata=metadata,
    )
