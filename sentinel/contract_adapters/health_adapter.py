"""Adapter for the health vocabularies used by existing V2 modules."""

from datetime import datetime
from enum import Enum

from sentinel.contracts import HealthStateV1, HealthStatusV1

from .authority_adapter import (
    AdaptedContractV1,
    build_adapter_metadata,
    validate_non_authoritative_source,
)

_HEALTH_MAP = {
    "HEALTHY": HealthStateV1.HEALTHY,
    "OBSERVING": HealthStateV1.OBSERVING,
    "WARNING": HealthStateV1.WARNING,
    "UNSTABLE": HealthStateV1.DEGRADED,
    "DEGRADED": HealthStateV1.DEGRADED,
    "CRITICAL": HealthStateV1.CRITICAL,
    "FAILED": HealthStateV1.CRITICAL,
}


def adapt_health(
    source: object,
    *,
    correlation_id: str,
    state: str | Enum | None = None,
    timestamp: datetime | None = None,
) -> AdaptedContractV1[HealthStatusV1]:
    """Normalize a legacy V2 health value into the central vocabulary."""

    validate_non_authoritative_source(source)
    raw_state = state if state is not None else getattr(source, "state", source)
    normalized = raw_state.value if isinstance(raw_state, Enum) else str(raw_state)
    try:
        health_state = _HEALTH_MAP[normalized.upper()]
    except KeyError as exc:
        raise ValueError(f"unsupported health state: {normalized}") from exc
    metadata = build_adapter_metadata(
        source,
        correlation_id=correlation_id,
        timestamp=timestamp,
    )
    return AdaptedContractV1(
        contract=HealthStatusV1(state=health_state),
        metadata=metadata,
    )
